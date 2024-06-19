# -*- coding: utf-8 -*-
"""
TencentBlueKing is pleased to support the open source community by making
蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except
in compliance with the License. You may obtain a copy of the License at

    http://opensource.org/licenses/MIT

Unless required by applicable law or agreed to in writing, software distributed under
the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the specific language governing permissions and
limitations under the License.

We undertake not to change the open source license (MIT license) applicable
to the current version of the project delivered to anyone in the future.
"""
from textwrap import dedent

import pytest
import yaml

from paas_wl.bk_app.applications.models import WlApp
from paas_wl.bk_app.processes.constants import ProbeType
from paas_wl.bk_app.processes.models import ProcessProbe
from paasng.platform.declarative.handlers import CNativeAppDescriptionHandler, DescriptionHandler
from paasng.platform.declarative.handlers import get_desc_handler as _get_desc_handler

pytestmark = pytest.mark.django_db(databases=["default", "workloads"])


@pytest.fixture()
def yaml_content():
    return dedent(
        """
        specVersion: 3
        appVersion: "1.0"
        modules:
        - name: default
          language: NodeJS
          sourceDir: src/frontend
          isDefault: True
          spec:
            processes:
            - name: web
              replicas: 1
              command:
              - npm
              args:
              - run
              - server
              resQuotaPlan: 4C1G
              probes:
                liveness:
                  exec:
                    command:
                    - cat
                    - /tmp/healthy
                readiness:
                  tcpSocket:
                    port: ${PORT}
        """
    )


@pytest.fixture()
def yaml_content_after_change():
    return dedent(
        """
        specVersion: 3
        appVersion: "1.0"
        modules:
        - name: default
          language: NodeJS
          sourceDir: src/frontend
          isDefault: True
          spec:
            processes:
            - name: web
              replicas: 2
              command:
              - npm
              args:
              - run
              - server
              resQuotaPlan: 4C1G
              probes:
                liveness:
                  exec:
                    command:
                    - cat
                    - /tmp/healthy
                startup:
                  tcpSocket:
                    port: ${PORT}
        """
    )


def get_desc_handler(yaml_content: str) -> DescriptionHandler:
    handler = _get_desc_handler(yaml.safe_load(yaml_content))
    assert isinstance(handler, CNativeAppDescriptionHandler)
    return handler


class TestSaasProbes:
    def test_saas_probes(self, bk_deployment, yaml_content):
        """验证 saas 应用探针对象 ProcessProbe 成功创建"""
        # bk_deployment.app_environment  外键未实例化，补全
        name = bk_deployment.app_environment.engine_app.name
        region = bk_deployment.app_environment.engine_app.region
        wlapp = WlApp.objects.create(name=name, region=region)

        get_desc_handler(yaml_content).handle_deployment(bk_deployment)
        liveness_probe: ProcessProbe = ProcessProbe.objects.get(
            app=wlapp, process_type="web", probe_type=ProbeType.LIVENESS
        )
        readiness_probe: ProcessProbe = ProcessProbe.objects.get(
            app=wlapp, process_type="web", probe_type=ProbeType.READINESS
        )

        assert liveness_probe.probe_handler
        assert liveness_probe.probe_handler.exec.command == ["cat", "/tmp/healthy"]

        assert readiness_probe.probe_handler
        assert readiness_probe.probe_handler.tcp_socket.port == "${PORT}"

    @pytest.mark.parametrize("_mock_delete_process_probe", [True], indirect=True)
    def test_saas_probes_changes(self, bk_deployment, bk_deployment_full, yaml_content, yaml_content_after_change):
        """验证 saas 应用探针对象 ProcessProbe 成功修改"""
        # bk_deployment.app_environment  外键未实例化，补全
        name = bk_deployment.app_environment.engine_app.name
        region = bk_deployment.app_environment.engine_app.region
        wlapp = WlApp.objects.create(name=name, region=region)

        # bk_deployment_full.app_environment  外键未实例化，补全
        bk_deployment_full.app_environment.engine_app.name = name
        bk_deployment_full.app_environment.engine_app.region = region

        get_desc_handler(yaml_content).handle_deployment(bk_deployment_full)
        # 模拟重新部署过程
        get_desc_handler(yaml_content_after_change).handle_deployment(bk_deployment_full)

        # liveness_probe 无变化
        liveness_probe: ProcessProbe = ProcessProbe.objects.get(
            app=wlapp, process_type="web", probe_type=ProbeType.LIVENESS
        )
        # readiness_probe 被删除
        readiness_probe_exists: ProcessProbe = ProcessProbe.objects.filter(
            app=wlapp, process_type="web", probe_type=ProbeType.READINESS
        ).exists()
        # start_probe 新增
        start_probe: ProcessProbe = ProcessProbe.objects.get(
            app=wlapp, process_type="web", probe_type=ProbeType.STARTUP
        )

        assert liveness_probe.probe_handler
        assert liveness_probe.probe_handler.exec.command == ["cat", "/tmp/healthy"]

        assert not readiness_probe_exists

        assert start_probe.probe_handler
        assert start_probe.probe_handler.tcp_socket.port == "${PORT}"
