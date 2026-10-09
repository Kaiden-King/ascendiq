from django.urls import path

from . import views

urlpatterns = [
    path("", views.hub_index, name="hub_index"),
    path("<slug:slug>/", views.hub_page, name="hub_page"),
]
