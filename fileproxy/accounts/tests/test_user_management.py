"""Tests for beta signup flow and staff-only UserViewSet."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from subscription.models import SubscriptionPlan, UserSubscription


# ---------------------------------------------------------------------------
# Beta signup view
# ---------------------------------------------------------------------------


class BetaSignupViewTests(TestCase):
    def _enable_beta(self, enabled=True):
        from django.test import override_settings

        return override_settings(BETA_ENABLED=enabled)

    def test_beta_signup_404_when_disabled(self):
        with self._enable_beta(False):
            resp = self.client.get("/accounts/beta/")
        self.assertEqual(resp.status_code, 404)

    def test_beta_signup_get_renders_form(self):
        with self._enable_beta():
            resp = self.client.get("/accounts/beta/")
        self.assertEqual(resp.status_code, 200)

    def test_beta_signup_creates_inactive_pending_user(self):
        with self._enable_beta():
            resp = self.client.post(
                "/accounts/beta/",
                {
                    "username": "betauser",
                    "first_name": "Beta",
                    "last_name": "User",
                    "email": "beta@example.com",
                    "password1": "securepassword123",
                    "password2": "securepassword123",
                },
            )
        self.assertRedirects(resp, "/accounts/beta/pending/")

        user = User.objects.get(username="betauser")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_authenticated and self.client.session.get("_auth_user_id"))

        profile = user.profile
        self.assertEqual(profile.status, UserProfile.STATUS_PENDING)
        self.assertEqual(profile.signup_source, UserProfile.SOURCE_BETA)

    def test_beta_pending_page_accessible_without_login(self):
        resp = self.client.get("/accounts/beta/pending/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# UserViewSet — permissions
# ---------------------------------------------------------------------------


class UserViewSetPermissionTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("admin", password="pass", is_staff=True)
        self.regular = User.objects.create_user("alice", password="pass")

    def test_list_requires_staff(self):
        self.client.login(username="alice", password="pass")
        resp = self.client.get("/api/v1/users/")
        self.assertEqual(resp.status_code, 403)

    def test_list_unauthenticated_returns_403(self):
        resp = self.client.get("/api/v1/users/")
        # DRF returns 403 for unauthenticated with our auth classes
        self.assertIn(resp.status_code, [401, 403])

    def test_list_staff_ok(self):
        self.client.login(username="admin", password="pass")
        resp = self.client.get("/api/v1/users/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# UserViewSet — status filter
# ---------------------------------------------------------------------------


class UserViewSetFilterTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("admin", password="pass", is_staff=True)
        self.client.login(username="admin", password="pass")

        self.pending_user = User.objects.create_user("pending_u", password="pass", is_active=False)
        UserProfile.objects.create(
            user=self.pending_user,
            status=UserProfile.STATUS_PENDING,
            signup_source=UserProfile.SOURCE_BETA,
        )

        self.active_user = User.objects.create_user("active_u", password="pass")
        UserProfile.objects.create(
            user=self.active_user,
            status=UserProfile.STATUS_ACTIVE,
            signup_source=UserProfile.SOURCE_NORMAL,
        )

        # User with no profile (normal signup, no profile created)
        self.no_profile_user = User.objects.create_user("noprofile_u", password="pass")

    def test_pending_filter(self):
        resp = self.client.get("/api/v1/users/?status=pending")
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.data]
        self.assertIn("pending_u", usernames)
        self.assertNotIn("active_u", usernames)

    def test_active_filter_includes_users_with_no_profile(self):
        resp = self.client.get("/api/v1/users/?status=active")
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.data]
        self.assertIn("active_u", usernames)
        self.assertIn("noprofile_u", usernames)
        self.assertNotIn("pending_u", usernames)

    def test_search_by_username(self):
        resp = self.client.get("/api/v1/users/?search=pending")
        self.assertEqual(resp.status_code, 200)
        usernames = [u["username"] for u in resp.data]
        self.assertIn("pending_u", usernames)
        self.assertNotIn("active_u", usernames)


# ---------------------------------------------------------------------------
# UserViewSet — approve / reject / suspend / activate
# ---------------------------------------------------------------------------


class UserViewSetActionTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("admin", password="pass", is_staff=True)
        self.client.login(username="admin", password="pass")

        self.target = User.objects.create_user("target", password="pass", is_active=False)
        self.profile = UserProfile.objects.create(
            user=self.target,
            status=UserProfile.STATUS_PENDING,
            signup_source=UserProfile.SOURCE_BETA,
        )

    def _url(self, action=""):
        base = f"/api/v1/users/{self.target.pk}/"
        return f"{base}{action}/" if action else base

    def test_approve_activates_user_and_assigns_beta_plan(self):
        resp = self.client.post(self._url("approve"))
        self.assertEqual(resp.status_code, 200)

        self.target.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(self.profile.status, UserProfile.STATUS_ACTIVE)

        sub = UserSubscription.objects.get(user=self.target)
        self.assertIsNotNone(sub.plan)
        self.assertEqual(sub.plan.name, "beta")

    def test_approve_normal_user_does_not_assign_beta_plan(self):
        normal = User.objects.create_user("norm", password="pass", is_active=False)
        UserProfile.objects.create(
            user=normal,
            status=UserProfile.STATUS_PENDING,
            signup_source=UserProfile.SOURCE_NORMAL,
        )
        resp = self.client.post(f"/api/v1/users/{normal.pk}/approve/")
        self.assertEqual(resp.status_code, 200)
        normal.refresh_from_db()
        self.assertTrue(normal.is_active)
        # Normal signup: no beta plan assigned
        self.assertFalse(UserSubscription.objects.filter(user=normal).exists())

    def test_approve_already_active_returns_400(self):
        self.profile.status = UserProfile.STATUS_ACTIVE
        self.profile.save()
        resp = self.client.post(self._url("approve"))
        self.assertEqual(resp.status_code, 400)

    def test_reject(self):
        self.target.is_active = True
        self.target.save()
        resp = self.client.post(self._url("reject"), {"note": "Not a good fit"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.profile.status, UserProfile.STATUS_REJECTED)
        self.assertEqual(self.profile.review_note, "Not a good fit")

    def test_suspend(self):
        self.target.is_active = True
        self.target.save()
        resp = self.client.post(self._url("suspend"), {"note": "Violation"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.profile.status, UserProfile.STATUS_SUSPENDED)

    def test_activate_suspended_user(self):
        self.target.is_active = False
        self.target.save()
        self.profile.status = UserProfile.STATUS_SUSPENDED
        self.profile.save()

        resp = self.client.post(self._url("activate"))
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(self.profile.status, UserProfile.STATUS_ACTIVE)

    def test_activate_pending_user_returns_400(self):
        """activate endpoint is only for suspended; pending users must use approve."""
        resp = self.client.post(self._url("activate"))
        self.assertEqual(resp.status_code, 400)

    def test_cannot_delete_own_account(self):
        resp = self.client.delete(f"/api/v1/users/{self.staff.pk}/")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_suspend_own_account(self):
        resp = self.client.post(f"/api/v1/users/{self.staff.pk}/suspend/")
        self.assertEqual(resp.status_code, 400)

    def test_get_user_invalid_pk_returns_404(self):
        resp = self.client.get("/api/v1/users/not-a-number/")
        self.assertEqual(resp.status_code, 404)

    def test_delete_user(self):
        resp = self.client.delete(self._url())
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    def test_change_plan(self):
        plan = SubscriptionPlan.objects.create(name="test-plan")
        resp = self.client.post(self._url("change-plan"), {"plan_id": str(plan.id)}, format="json")
        self.assertEqual(resp.status_code, 200)
        sub = UserSubscription.objects.get(user=self.target)
        self.assertEqual(sub.plan, plan)

    def test_change_plan_missing_plan_id_returns_400(self):
        resp = self.client.post(self._url("change-plan"), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_partial_update_user(self):
        resp = self.client.patch(self._url(), {"first_name": "Updated"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Updated")
