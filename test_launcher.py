import json
import os
import pathlib
import sqlite3
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import launcher


class ConfigurationTests(unittest.TestCase):
    def test_codex_switch_preserves_projects_and_other_providers(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = pathlib.Path(temporary)
            config = home / 'config.toml'
            config.write_text('model = "old"\n[projects."/example"]\ntrust_level = "trusted"\n')
            database = home / 'state_5.sqlite'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE threads(model_provider TEXT)')
                db.executemany('INSERT INTO threads VALUES (?)', [('openai',), ('other',)])
            settings = {'home': temporary, 'api_base_url': 'https://gateway.example/v1',
                        'api_model': 'example-model', 'sync_thread_provider': True}
            launcher.codex_config(settings, 'api')
            parsed = tomllib.loads(config.read_text())
            self.assertEqual(parsed['projects']['/example']['trust_level'], 'trusted')
            self.assertEqual(parsed['model_provider'], 'ai_gateway')
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT * FROM threads').fetchall(), [('ai_gateway',), ('other',)])
            launcher.codex_config(settings, 'account')
            self.assertNotIn('model_provider', tomllib.loads(config.read_text()))
            self.assertTrue(list(home.glob('config.toml.bak-*')))
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_claude_models_and_account_mode(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'HOME': temporary}):
            settings = {'api_base_url': 'https://gateway.example', 'api_key': 'test-placeholder',
                        'models': ['first-example', 'second-example']}
            launcher.claude_config(settings, 'api')
            directory = pathlib.Path(temporary) / 'Library/Application Support/Claude-3p'
            meta = json.loads((directory / 'configLibrary/_meta.json').read_text())
            profile = json.loads((directory / 'configLibrary' / (meta['appliedId'] + '.json')).read_text())
            self.assertEqual(profile['inferenceModels'], settings['models'])
            launcher.claude_config(settings, 'account')
            self.assertEqual(json.loads((directory / 'claude_desktop_config.json').read_text())['deploymentMode'], '1p')

    def test_http_gateway_rejected(self):
        with self.assertRaises(ValueError):
            launcher.https_url('http://gateway.example')


if __name__ == '__main__':
    unittest.main()
