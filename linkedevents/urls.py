from django.conf import settings
from django.urls import path, re_path, reverse, include
from django.views.generic import RedirectView

from .api import LinkedEventsAPIRouter
from helusers.admin_site import admin

api_router = LinkedEventsAPIRouter()


class RedirectToAPIRootView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse('api-root', kwargs={'version': 'v1'})


urlpatterns = [
    re_path(r'^(?P<version>(v0.1|v1))/', include(api_router.urls)),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^accounts/', include('allauth.urls')),
    re_path(r'^$', RedirectToAPIRootView.as_view()),
    path('', include('social_django.urls', namespace='social')),
    path('', include('helusers.urls', 'helusers'))
]


if settings.USE_SWAGGER_OPENAPI_VIEW:
    from rest_framework import permissions
    from drf_yasg.views import get_schema_view
    from drf_yasg import openapi as drf_openapi
    openapi = drf_openapi.Info(
        title="LinkedEvents API View",
        default_version='v1',
        description="LinkedEvents API Documentation",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=drf_openapi.Contact(email="sovellustuki@turku.fi"),
        license=drf_openapi.License(name="MIT License"),
    )
    schema_view = get_schema_view(
        openapi,
        public=True,
        permission_classes=(permissions.AllowAny,),
    )
    urlpatterns.extend([
        re_path(r'api(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
        re_path(r'api/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        re_path(r'redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ])