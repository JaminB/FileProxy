from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from subscription.service import get_or_create_beta_plan, switch_plan

from ..models import APIKey, UserProfile
from ..tokens import APIKeyToken
from .serializers import (
    APIKeyCreateSerializer,
    APIKeyListSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)


class APIKeyViewSet(viewsets.ViewSet):
    def list(self, request):
        keys = APIKey.objects.filter(user=request.user)
        return Response(APIKeyListSerializer(keys, many=True).data)

    def create(self, request):
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key = APIKey.objects.create(
            user=request.user,
            name=serializer.validated_data["name"],
        )
        token = APIKeyToken.for_api_key(api_key)
        data = APIKeyListSerializer(api_key).data
        data["token"] = str(token)
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        try:
            api_key = APIKey.objects.get(pk=pk, user=request.user)
        except (APIKey.DoesNotExist, ValueError, ValidationError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        api_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ViewSet):
    """Staff-only user management endpoints."""

    def _require_staff(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return None

    def _get_user(self, pk):
        try:
            return User.objects.select_related("profile", "subscription__plan").get(pk=pk)
        except (User.DoesNotExist, ValueError, ValidationError):
            return None

    def _get_or_create_profile(self, user):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "status": UserProfile.STATUS_ACTIVE,
                "signup_source": UserProfile.SOURCE_NORMAL,
            },
        )
        return profile

    def list(self, request):
        denied = self._require_staff(request)
        if denied:
            return denied

        qs = User.objects.select_related("profile", "subscription__plan").order_by("-date_joined")

        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter == "active":
                # Include users with no profile (treated as active) and those explicitly active
                qs = qs.filter(
                    Q(profile__isnull=True) | Q(profile__status=UserProfile.STATUS_ACTIVE)
                )
            else:
                qs = qs.filter(profile__status=status_filter)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        return Response(UserListSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(UserListSerializer(user).data)

    def partial_update(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user.refresh_from_db()
        return Response(UserListSerializer(user).data)

    def destroy(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if user == request.user:
            return Response(
                {"detail": "Cannot delete your own account."}, status=status.HTTP_400_BAD_REQUEST
            )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)

        profile = self._get_or_create_profile(user)
        if profile.status not in (UserProfile.STATUS_PENDING, UserProfile.STATUS_REJECTED):
            return Response(
                {"detail": "User is not pending approval."}, status=status.HTTP_400_BAD_REQUEST
            )

        user.is_active = True
        user.save(update_fields=["is_active"])
        profile.set_status(UserProfile.STATUS_ACTIVE)

        # Only assign the beta plan for users who signed up via the beta flow
        if profile.signup_source == UserProfile.SOURCE_BETA:
            switch_plan(user, get_or_create_beta_plan())

        user.refresh_from_db()
        return Response(UserListSerializer(user).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)

        note = request.data.get("note", "")
        profile = self._get_or_create_profile(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        profile.set_status(UserProfile.STATUS_REJECTED, note=note)
        user.refresh_from_db()
        return Response(UserListSerializer(user).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if user == request.user:
            return Response(
                {"detail": "Cannot suspend your own account."}, status=status.HTTP_400_BAD_REQUEST
            )

        note = request.data.get("note", "")
        profile = self._get_or_create_profile(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        profile.set_status(UserProfile.STATUS_SUSPENDED, note=note)
        user.refresh_from_db()
        return Response(UserListSerializer(user).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Re-activate a suspended user. For pending/rejected users use approve instead."""
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)

        profile = self._get_or_create_profile(user)
        if profile.status != UserProfile.STATUS_SUSPENDED:
            return Response(
                {"detail": "Only suspended users can be activated via this endpoint. Use approve for pending/rejected users."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])
        profile.set_status(UserProfile.STATUS_ACTIVE)
        user.refresh_from_db()
        return Response(UserListSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not user.email:
            return Response(
                {"detail": "User has no email address."}, status=status.HTTP_400_BAD_REQUEST
            )

        form = PasswordResetForm({"email": user.email})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                from_email=None,
                email_template_name="registration/password_reset_email.html",
            )
        return Response({"detail": "Password reset email sent."})

    @action(detail=True, methods=["post"], url_path="change-plan")
    def change_plan(self, request, pk=None):
        denied = self._require_staff(request)
        if denied:
            return denied

        user = self._get_user(pk)
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)

        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response({"detail": "plan_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        from subscription.models import SubscriptionPlan

        try:
            plan = SubscriptionPlan.objects.get(pk=plan_id)
        except (SubscriptionPlan.DoesNotExist, ValueError, ValidationError):
            return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

        switch_plan(user, plan)
        user.refresh_from_db()
        return Response(UserListSerializer(user).data)
