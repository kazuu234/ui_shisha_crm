from django.urls import include, path

app_name = "ui"

urlpatterns = [
    path("s/", include("ui.staff.urls")),
]
