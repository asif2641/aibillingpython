"""
categories/urls.py
==================
URL routing for Category and Unit management.
"""

from django.urls import path

from . import views

app_name = "categories"

urlpatterns = [
    path("", views.category_list_view, name="category_list"),
    path("add/", views.category_add_view, name="category_add"),
    path("<int:pk>/edit/", views.category_edit_view, name="category_edit"),
    path("<int:pk>/archive/", views.category_archive_view, name="category_archive"),
    path("units/", views.unit_list_view, name="unit_list"),
    path("units/add/", views.unit_add_view, name="unit_add"),
]
