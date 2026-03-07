from rest_framework import status, viewsets
from rest_framework.response import Response

from ..models import APIKey
from ..tokens import APIKeyToken
from .serializers import APIKeyCreateSerializer, APIKeyListSerializer


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
        except (APIKey.DoesNotExist, Exception):
            return Response(status=status.HTTP_404_NOT_FOUND)
        api_key.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
