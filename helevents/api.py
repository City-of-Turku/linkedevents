from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions, serializers, generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django_orghierarchy.models import Organization
from django.db.models import Q


all_views = []


def register_view(klass, name, basename=None):
    entry = {'class': klass, 'name': name}
    if basename is not None:
        entry['basename'] = basename
    all_views.append(entry)


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.ReadOnlyField(source='get_display_name')

    def to_representation(self, obj):
        rep = super(UserSerializer, self).to_representation(obj)
        default_org = obj.get_default_organization()
        if default_org:
            rep['organization'] = default_org.id
        rep['admin_organizations'] = [org.id for org in obj.admin_organizations.all()]
        rep['organization_memberships'] = [org.id for org in obj.organization_memberships.all()]
        rep['public_memberships'] = [org.id for org in obj.public_memberships.all()]
        return rep

    class Meta:
        fields = [
            'last_login', 'username', 'email', 'date_joined',
            'pk', 'first_name', 'last_name', 'uuid', 'department_name',
            'is_staff', 'display_name',
        ]
        model = get_user_model()


ADMIN = 'admin'
REGULAR = 'regular'
PRIVATE = 'private'
ORGANIZATION_LEVELS = (ADMIN, REGULAR, PRIVATE)

class UserViewSet(viewsets.ModelViewSet):

    @action(detail=True, methods=['put'])
    def update_organization_levels(self, request, pk=None, **kwargs):
        organization = self._get_organization(request.data.get('organization'))
        user = self.get_object()
        if not user.is_superuser and not user.is_admin(organization):
            raise PermissionDenied('You do not have rights to this organization')

        user_to_update = self._get_user(pk)
        org_levels = request.data.get('organization_levels')
        self._validate_organization_levels(org_levels)

        if org_levels[ADMIN]:
            organization.admin_users.add(user_to_update)
        else:
            organization.admin_users.remove(user_to_update)

        if org_levels[REGULAR]:
            organization.regular_users.add(user_to_update)
        else:
            organization.regular_users.remove(user_to_update)

        if org_levels[PRIVATE]:
            organization.private_users.add(user_to_update)
        else:
            organization.private_users.remove(user_to_update)
        
        user_data = UserSerializer(user_to_update).data
        return Response(user_data, status=status.HTTP_200_OK)


    def _get_organization(self, org_id):
        if not org_id:
            raise serializers.ValidationError({'organization': 'must be given'})
        try:
            organization = Organization.objects.get(id=org_id)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({'organization': 'not found'})
        return organization


    def _get_user(self, username):
        try:
            user = self.queryset.get(username=username)
        except ObjectDoesNotExist:
            raise serializers.ValidationError({'user': 'not found'})
        return user


    def _validate_organization_levels(self, levels):
        if not levels:
            raise serializers.ValidationError({'organization_levels': 'must be included'})

        if not isinstance(levels, dict):
            raise serializers.ValidationError({'organization_levels': 'must be type object'})
        
        org_level_keys = levels.keys()
        if len(org_level_keys) != len(ORGANIZATION_LEVELS):
            raise serializers.ValidationError(
                {'organization_levels': f'must contain values for each level {ORGANIZATION_LEVELS}'}
            )
        for org_level in ORGANIZATION_LEVELS:
            if org_level not in org_level_keys:
                raise serializers.ValidationError(
                    {'organization_levels': f'must contain values for each level {ORGANIZATION_LEVELS}'}
                )
        for org_level_value in levels.values():
            if not isinstance(org_level_value, bool):
                raise serializers.ValidationError(
                    {'organization_levels': 'each level value must be type boolean'}
                )


    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        email = self.request.query_params.get('email')
    
        if email:
            queryset = queryset.filter(email=email)
        
        org_id = self.request.query_params.get('organization')
        if org_id:
            if user.is_superuser or user.is_admin(self._get_organization(org_id)):
                return queryset.filter(
                    Q(admin_organizations=org_id)
                    | Q(organization_memberships=org_id)
                    | Q(public_memberships=org_id)
                ).distinct()
            else:
                return queryset.none()

        if user.is_superuser or (user.is_admin(user.get_default_organization()) and email):
            return queryset
        else:
            return queryset.filter(pk=user.pk)

    def get_object(self):
        username = self.kwargs.get('username', None)
        if username:
            qs = self.get_queryset()
            obj = generics.get_object_or_404(qs, username=username)
        else:
            obj = self.request.user
        return obj

    permission_classes = [permissions.IsAuthenticated]
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer


register_view(UserViewSet, 'user')
