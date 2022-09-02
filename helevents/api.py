from django.contrib.auth import get_user_model
from rest_framework import permissions, serializers, generics, viewsets


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


class UserViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        email = self.request.query_params.get('email')
    
        if email is not None:
            queryset = queryset.filter(email=email)

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
