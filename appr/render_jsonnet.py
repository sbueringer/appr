from __future__ import absolute_import, division, print_function

import json
import logging
import os
import os.path
import re

import _jsonnet
import jinja2
import yaml

import appr.template_filters as filters
from appr.utils import convert_utf8

logger = logging.getLogger(__name__)

with open(os.path.join(os.path.dirname(__file__), "jsonnet/manifest.jsonnet.j2")) as f:
    JSONNET_TEMPLATE = f.read()


def yaml_to_jsonnet(manifestyaml, tla_codes=None):
    jinja_env = jinja2.Environment()
    jinja_env.filters.update(filters.jinja_filters())
    # 1. Resolve old manifest variables
    # Load 'old' manifest.yaml
    v = {"manifest": convert_utf8(json.loads(json.dumps(yaml.load(manifestyaml))))}
    # Get variable from the 'old' manfiest and update  them
    variables = v['manifest'].get("variables", {})
    if tla_codes is not None and 'params' in tla_codes:
        tla = json.loads(tla_codes['params']).get("variables", {})
        variables.update(tla)
    # Resolve the templated variables inside the 'old' manifest
    manifest_tpl = jinja_env.from_string(manifestyaml)

    # 2. Convert 'old' manifest.yaml to manifest.jsonnet
    rendered_manifestyaml = manifest_tpl.render(variables)
    v = {"manifest": convert_utf8(json.loads(json.dumps(yaml.load(rendered_manifestyaml))))}
    # Load the yaml -> jsonnet template
    template = jinja_env.from_string(JSONNET_TEMPLATE)
    templatedjsonnet = template.render(v)
    # @TODO keep yaml format and escape 'jsonnet' commands:  key: "<% $.variables.key %>"
    # jsonnet_str = re.sub(r'[\'"]<%(.*)%>["\']', r"\1", templatedjsonnet)
    return templatedjsonnet


class RenderJsonnet(object):

    def __init__(self, files=None, manifestpath=None):
        self.manifestdir = None
        if manifestpath:
            self.manifestdir = os.path.dirname(manifestpath)
        self.files = files

    #  Returns content if worked, None if file not found, or throws an exception
    def try_path(self, path, rel):
        if not rel:
            raise RuntimeError('Got invalid filename (empty string).')

        libfilepath = os.path.join(os.path.dirname(__file__), "jsonnet/lib/%s" % rel)

        if self.files is not None and rel in self.files:
            if self.files[rel] is None:
                with open(rel) as f:
                    self.files[rel] = f.read()
            return rel, self.files[rel]
        elif os.path.isfile(libfilepath):
            with open(libfilepath) as f:
                return rel, f.read()
        elif self.manifestdir:
            filepath = os.path.join(self.manifestdir, rel)
            if os.path.isfile(filepath):
                with open(filepath) as f:
                    return rel, f.read()

        if rel[0] == '/':
            full_path = rel
        else:
            full_path = path + rel
        if full_path[-1] == '/':
            raise RuntimeError('Attempted to import a directory')
        if not os.path.isfile(full_path):
            return full_path, None
        with open(full_path) as f:
            return full_path, f.read()

    def import_callback(self, path, rel):
        full_path, content = self.try_path(path, rel)
        if content:
            return full_path, content
        raise RuntimeError('File not found')

    def render_jsonnet(self, manifeststr, tla_codes=None):
        try:
            json_str = _jsonnet.evaluate_snippet(
                "snippet", manifeststr, import_callback=self.import_callback,
                native_callbacks=filters.jsonnet_callbacks(), tla_codes=tla_codes)

        except RuntimeError as e:
            print("tla_codes: %s" % (str(tla_codes)))
            print("\n".join([
                "%s %s" % (i, line) for i, line in enumerate(
                    [l for l in manifeststr.split("\n") if re.match(r"^ *#", l) is None])
            ]))
            raise e
        return json.loads(json_str)
