import json
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from .supersetapiclient.client import SupersetClient

logger = logging.getLogger('django')

DATA_CACHE_TIMEOUT = 5 * 60

class SupersetDashboard:
    
    def __init__(self, superset_dashboard_name):
        self.superset_dashboard_name = superset_dashboard_name
        self.client = self.get_cleint()
        
    def get_details(self):
        
        details = cache.get(f"_{self.superset_dashboard_name}")
        if details is None:
            try:
                dashboards = self.client.dashboards.find(dashboard_title=self.superset_dashboard_name)
                details = None
                if isinstance(dashboards, list) and len(dashboards) > 0:
                    dashboard = dashboards[0]
                    details = {
                        "position": dashboard.position_json,
                        "title": dashboard.dashboard_title,
                        "charts": [
                            self.get_chart(chart_id) for chart_id in dashboard.get_charts()
                        ]
                    }
                
                cache.set(f"_{self.superset_dashboard_name}", details, DATA_CACHE_TIMEOUT)
            except Exception as ex:
                logger.exception(ex)
                details = None

        return details

    def get_cleint(self):
        client = SupersetClient(
            host=settings.SUPERSET_URL,
            username=settings.SUPERSET_USERNAME,
            password=settings.SUPERSET_PASSWORD
        )
        return client

    def get_chart(self, chart_id):
        chart = self.client.charts.get(chart_id)
        
        chart_params = chart.params
        query_context = chart.query_context
        if 'form_data' in query_context:
            query_context.pop('form_data')
        queries = query_context.get('queries', [])
        for query in queries:
            extras = query.get('extras')
            if 'time_range_endpoints' in extras:
                extras.pop('time_range_endpoints')

        chart_data_url = chart.test_connection_url.replace(str(chart.id), 'data')

        chart_data = self.client.post(
            url=chart_data_url,
            json=query_context
        ).json()

        if isinstance(chart_data, dict) and len(chart_data.get('result', [])) > 0:
            chart_data = chart_data['result'][0]
        else:
            chart_data = {}

        chart_details = {
            "name": chart.slice_name,
            "header_font_size": chart_params.get("header_font_size"),
            "viz_type": chart_params.get("viz_type"),
            "metric": chart_params.get("metric"),
            "show_timestamp": chart_params.get("show_timestamp"),
            "show_trend_line": chart_params.get("show_trend_line"),
            "start_y_axis_at_zero": chart_params.get("start_y_axis_at_zero"),
            "subheader_font_size": chart_params.get("subheader_font_size"),
            "time_format": chart_params.get("time_format"),
            "time_grain_sqla": chart_params.get("time_grain_sqla"),
            "time_range": chart_params.get("time_range"),
            "y_axis_format": chart_params.get("y_axis_format"),
            "data": {
                "from_dttm": chart_data.get("from_dttm"),
                "to_dttm": chart_data.get("to_dttm"),
                "rowcount": chart_data.get("rowcount"),
                "colnames": chart_data.get("colnames"),
                "data": chart_data.get("data"),
            }
        }
        return chart_details
