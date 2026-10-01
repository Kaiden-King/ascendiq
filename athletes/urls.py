from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("workout/today/", views.workout_today, name="workout_today"),
    path("workout/start/", views.workout_start, name="workout_start"),
    path("workout/<int:workout_id>/", views.workout_session, name="workout_session"),
    path("workout/set/<int:set_id>/toggle/", views.set_toggle, name="set_toggle"),
    path("workout/set/<int:set_id>/score/", views.set_score, name="set_score"),
]
