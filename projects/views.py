from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsOwner
from accounts.serializers import TimeEntrySerializer
from projects.models import Project
from projects.serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filterset_fields = ["status", "client"]

    def get_queryset(self):
        qs = (
            Project.objects.filter(owner=self.request.user)
            .select_related("client")
            .prefetch_related("time_entries")
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """Budget burn-down for a project."""
        project = self.get_object()
        return Response(
            {
                "project": ProjectSerializer(project).data,
                "hours_logged": project.hours_logged,
                "earned": project.earned,
                "budget": float(project.budget) if project.budget is not None else None,
                "budget_remaining": project.budget_remaining,
                "is_over_budget": project.is_over_budget,
            }
        )

    @action(detail=True, methods=["post"])
    def log_time(self, request, pk=None):
        """Log time against this project in one call."""
        project = self.get_object()
        serializer = TimeEntrySerializer(
            data={**request.data, "client": project.client_id, "project": project.id},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(owner=request.user)
        return Response(TimeEntrySerializer(entry).data, status=201)
