from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from accounting.views import (
    client_portal,
    download_management_report,
    hmrc_authorise,
    hmrc_callback,
    hmrc_sandbox_status_view,
    practice_dashboard,
)

urlpatterns = [
    path('', client_portal, name='client_portal'),
    path('practice/', practice_dashboard, name='practice_dashboard'),
    path(
        'reports/<uuid:tenant_id>/<str:file_format>/',
        download_management_report,
        name='download_management_report',
    ),
    path(
        'integrations/hmrc/',
        hmrc_sandbox_status_view,
        name='hmrc_sandbox_status',
    ),
    path(
        'api/integrations/hmrc/authorise/',
        hmrc_authorise,
        name='hmrc_authorise',
    ),
    path(
        'api/integrations/hmrc/callback',
        hmrc_callback,
        name='hmrc_callback',
    ),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True,
            next_page='client_portal',
        ),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('admin/', admin.site.urls),
]
