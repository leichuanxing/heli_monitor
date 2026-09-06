from django.db import models


class SystemSetting(models.Model):
    brand_logo_text = models.CharField(max_length=32, default="合力数据")
    home_page_title = models.CharField(max_length=64, default="合力数据业务监控系统")
    browser_title = models.CharField(max_length=64, default="合力数据业务监控系统")
    login_page_description = models.CharField(
        max_length=128, default="企业级业务可用性监控与告警平台"
    )
    monitor_wall_title = models.CharField(max_length=64, default="合力数据业务监控系统")
    dashboard_refresh_seconds = models.PositiveIntegerField(default=30)
    monitor_wall_refresh_seconds = models.PositiveIntegerField(default=10)
    monitor_result_retention_count = models.PositiveIntegerField(default=10000)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting
