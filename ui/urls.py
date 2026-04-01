from django.urls import include, path

urlpatterns = [
    path("s/", include("ui.staff.urls", namespace="staff")),
    path("o/", include("ui.owner.urls", namespace="owner")),
]
