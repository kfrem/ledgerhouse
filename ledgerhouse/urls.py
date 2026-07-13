from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from accounting.views import (
    client_portal,
    client_vat_review,
    companies_house_workspace,
    download_management_report,
    hmrc_authorise,
    hmrc_callback,
    hmrc_sandbox_status_view,
    hmrc_vat_workspace,
    management_report_view,
    practice_banking_review,
    practice_client_detail,
    practice_clients,
    practice_dashboard,
    practice_evidence_review,
    practice_ledger_review,
)

urlpatterns = [
    path('', client_portal, name='client_portal'),
    path('vat/review/', client_vat_review, name='client_vat_review'),
    path('practice/', practice_dashboard, name='practice_dashboard'),
    path(
        'practice/banking/',
        practice_banking_review,
        name='practice_banking_review',
    ),
    path(
        'practice/ledger/',
        practice_ledger_review,
        name='practice_ledger_review',
    ),
    path(
        'practice/evidence/',
        practice_evidence_review,
        name='practice_evidence_review',
    ),
    path(
        'practice/clients/',
        practice_clients,
        name='practice_clients',
    ),
    path(
        'practice/clients/<uuid:tenant_id>/',
        practice_client_detail,
        name='practice_client_detail',
    ),
    path(
        'reports/<uuid:tenant_id>/',
        management_report_view,
        name='management_report',
    ),
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
        'integrations/hmrc/vat/',
        hmrc_vat_workspace,
        name='hmrc_vat_workspace',
    ),
    path(
        'integrations/companies-house/',
        companies_house_workspace,
        name='companies_house_workspace',
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
