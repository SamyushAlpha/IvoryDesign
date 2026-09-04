from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve
from Ivory import views
from Ivory.chat import ask
from Ivory import support_views


urlpatterns = [
    path('admin/support/api/<uuid:public_id>/assistant/', support_views.staff_assign_assistant, name='support_staff_assistant'),
    path('chatbox/support/start/', support_views.visitor_start, name='support_visitor_start'),
    path('chatbox/support/files/<uuid:public_id>/', support_views.attachment_download, name='support_attachment'),
    path('admin/support/', support_views.staff_inbox, name='support_inbox'),
    path('admin/support/api/conversations/', support_views.staff_conversations, name='support_staff_conversations'),
    path('admin/support/api/<uuid:public_id>/', support_views.staff_history, name='support_staff_history'),
    path('admin/support/api/<uuid:public_id>/claim/', support_views.staff_claim, name='support_staff_claim'),
    path('admin/support/api/<uuid:public_id>/reply/', support_views.staff_message, name='support_staff_message'),
    path('admin/support/api/<uuid:public_id>/resolve/', support_views.staff_resolve, name='support_staff_resolve'),
    path('admin/', admin.site.urls),

    path('', views.home, name='home'),

    path('contact/', views.contact, name='contact'),

    path('chatbox/ask/', ask, name='chat_ask'),
    path('chatbox/support/history/', support_views.visitor_history, name='support_visitor_history'),
    path('chatbox/support/message/', support_views.visitor_message, name='support_visitor_message'),

    path('projects/', views.projects, name='projects'),

    path('about/', views.about, name='about'),
    path('services/', views.services, name='services'),
    path('team/<int:pk>/', views.team_portfolio, name='team_portfolio'),

]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
elif settings.IS_VERCEL:
    # Existing portfolio uploads are bundled read-only in the first deployment.
    # New production uploads should use an external Django storage backend.
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
