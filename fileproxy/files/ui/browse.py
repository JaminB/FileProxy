from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def browse(request):
    return render(request, "files_ui/browse.html")
