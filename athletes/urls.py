from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("history/", views.history, name="history"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("leaderboard/rankings/", views.rankings_board, name="rankings_board"),
    path("leaderboard/toggle/", views.leaderboard_toggle, name="leaderboard_toggle"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.settings_page, name="settings"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("profile/rankings/add/", views.ranking_add, name="ranking_add"),
    path("profile/rankings/<int:ranking_id>/delete/", views.ranking_delete, name="ranking_delete"),
    path("profile/highlights/add/", views.highlight_add, name="highlight_add"),
    path("profile/highlights/<int:highlight_id>/delete/", views.highlight_delete, name="highlight_delete"),
    path("workout/today/", views.workout_today, name="workout_today"),
    path("workout/start/", views.workout_start, name="workout_start"),
    path("workout/<int:workout_id>/", views.workout_session, name="workout_session"),
    path("workout/<int:workout_id>/finish/", views.workout_finish, name="workout_finish"),
    path("workout/<int:workout_id>/summary/", views.workout_summary, name="workout_summary"),
    path("workout/set/<int:set_id>/toggle/", views.set_toggle, name="set_toggle"),
    path("workout/set/<int:set_id>/score/", views.set_score, name="set_score"),
    path("workout/set/<int:set_id>/shot/", views.set_shot, name="set_shot"),
]
