from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from accounting.views import client_portal, practice_dashboard

urlpatterns = [
    path('', client_portal, name='client_portal'),
    path('practice/', practice_dashboard, name='practice_dashboard'),
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
