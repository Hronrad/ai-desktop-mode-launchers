#!/usr/bin/env python3
"""macOS desktop launchers. All deployment settings remain in a local file."""
import json
import os
import pathlib
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import uuid

ROOT = pathlib.Path(__file__).resolve().parent


def path(value):
    return pathlib.Path(value).expanduser()


def write_private(target, contents):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp-' + str(uuid.uuid4()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(contents)
    os.replace(temporary, target)


def save_json(target, data):
    write_private(target, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def backup(target):
    if target.exists():
        destination = target.with_name(target.name + '.bak-' + str(time.time_ns()))
        shutil.copyfile(target, destination)
        destination.chmod(0o600)


def https_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('API 网关必须是 HTTPS URL，且不能包含凭据')
    return value.rstrip('/')


def load_settings(client):
    location = path(os.environ.get('AI_DESKTOP_MODE_CONFIG', str(ROOT / 'config.json')))
    if not location.exists():
        raise ValueError('请先复制 config.example.json 为 config.json，填写配置并 chmod 600 config.json')
    if location.stat().st_mode & 0o077:
        raise ValueError('配置含凭据，请先执行 chmod 600 ' + str(location))
    return json.loads(location.read_text())[client]


def codex_config(settings, mode):
    home = path(settings.get('home', '~/.codex'))
    target = home / 'config.toml'
    original = target.read_text() if target.exists() else ''
    # Validate before editing; tomllib is available in Python 3.11+.
    import tomllib
    tomllib.loads(original)
    remove = {'forced_login_method', 'model_provider', 'model', 'model_catalog_json',
              'model_context_window', 'cli_auth_credentials_store'}
    lines, section = [], ''
    for line in original.splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            section = stripped
        if section == '[model_providers.ai_gateway]':
            continue
        if not section and stripped.split('=', 1)[0].strip() in remove:
            continue
        lines.append(line)
    prefix = ['forced_login_method = ' + json.dumps('api' if mode == 'api' else 'chatgpt'),
              'cli_auth_credentials_store = "file"']
    model = settings.get(mode + '_model', '')
    if model:
        prefix.append('model = ' + json.dumps(model))
    if mode == 'api':
        prefix.append('model_provider = "ai_gateway"')
        lines += ['', '[model_providers.ai_gateway]', 'name = "User API Gateway"',
                  'base_url = ' + json.dumps(https_url(settings['api_base_url'])),
                  'wire_api = "responses"', 'env_key = "CODEX_MODE_API_KEY"',
                  'requires_openai_auth = false', 'supports_websockets = false']
    updated = '\n'.join(prefix + lines) + '\n'
    tomllib.loads(updated)
    backup(target)
    write_private(target, updated)
    if settings.get('sync_thread_provider'):
        database = home / 'state_5.sqlite'
        if database.exists():
            with sqlite3.connect(database) as connection:
                columns = {row[1] for row in connection.execute('PRAGMA table_info(threads)')}
                if 'model_provider' not in columns:
                    print('会话数据库结构不兼容，跳过 provider 同步')
                else:
                    destination = database.with_name(database.name + '.bak-' + str(time.time_ns()))
                    with sqlite3.connect(destination) as copy:
                        connection.backup(copy)
                    destination.chmod(0o600)
                    connection.execute("UPDATE threads SET model_provider=? WHERE model_provider IN ('openai','ai_gateway')",
                                       ('ai_gateway' if mode == 'api' else 'openai',))
    return {'CODEX_HOME': str(home), 'CODEX_SQLITE_HOME': str(home)}


def claude_config(settings, mode):
    directory = path('~/Library/Application Support/Claude-3p')
    target = directory / 'claude_desktop_config.json'
    data = json.loads(target.read_text()) if target.exists() else {}
    data['deploymentMode'] = '3p' if mode == 'api' else '1p'
    if mode == 'api':
        library = directory / 'configLibrary'
        library.mkdir(parents=True, exist_ok=True)
        library.chmod(0o700)
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, 'ai-desktop-mode-launchers/user-gateway'))
        profile = {
            'inferenceProvider': 'gateway', 'inferenceCredentialKind': 'static',
            'inferenceGatewayBaseUrl': https_url(settings['api_base_url']),
            'inferenceGatewayApiKey': settings['api_key'],
            'inferenceGatewayAuthScheme': settings.get('auth_scheme', 'x-api-key'),
            'inferenceModels': settings['models'], 'modelDiscoveryEnabled': False,
            'claudeAiImport': {'enabled': True, 'exportEnabled': True, 'bannerBehavior': 'detect'},
        }
        hosts = settings.get('cowork_egress_allowed_hosts', [])
        if hosts:
            profile['coworkEgressAllowedHosts'] = hosts
        profile_file = library / (identifier + '.json')
        backup(profile_file)
        backup(library / '_meta.json')
        save_json(profile_file, profile)
        save_json(library / '_meta.json', {'appliedId': identifier})
    backup(target)
    save_json(target, data)
    return {}


def launch(client, settings, mode):
    app = path(settings['app'])
    if not app.is_dir():
        raise ValueError('找不到客户端：' + str(app))
    if mode == 'api':
        https_url(settings.get('api_base_url', ''))
        if not settings.get('api_key'):
            raise ValueError('请填写 api_key')
        if client == 'claude' and not settings.get('models'):
            raise ValueError('请填写 models，第一项为默认模型')
        if client == 'codex' and not settings.get('api_model'):
            raise ValueError('请填写 api_model')
    executable = app / 'Contents/MacOS'
    # Quit only the selected app; wait before changing its configuration.
    subprocess.run(['osascript', '-e', 'tell application ' + json.dumps(str(app)) + ' to quit'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if subprocess.run(['pgrep', '-f', str(executable)], stdout=subprocess.DEVNULL).returncode:
            break
        time.sleep(0.2)
    else:
        raise ValueError('客户端尚未退出，请关闭后重试')
    additions = codex_config(settings, mode) if client == 'codex' else claude_config(settings, mode)
    if client == 'codex' and mode == 'api':
        additions['CODEX_MODE_API_KEY'] = settings['api_key']
        if settings.get('ca_certificate'):
            additions['CODEX_CA_CERTIFICATE'] = str(path(settings['ca_certificate']))
    environment = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE', 'CODEX_API_AUTH_FILE',
                'CODEX_CA_CERTIFICATE', 'CODEX_MODE_API_KEY', 'CLAUDE_USER_DATA_DIR'):
        environment.pop(key, None)
    proxy = settings.get(mode + '_proxy', '')
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        additions[key] = proxy
    additions.update({'NO_PROXY': 'localhost,127.0.0.1,::1', 'no_proxy': 'localhost,127.0.0.1,::1'})
    environment.update(additions)
    # Launch the app binary with an explicit environment; keep keys out of argv.
    with (app / 'Contents/Info.plist').open('rb') as stream:
        binary = plistlib.load(stream)['CFBundleExecutable']
    command = [str(executable / binary),
               '--proxy-server=' + proxy if proxy else '--no-proxy-server']
    subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    print(f'已启动 {client} 桌面客户端：{mode}；代理：' + ('已配置' if proxy else '直连'))


def main():
    client = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else ''
    if mode in ('-h', '--help', 'help'):
        print(f'{client}-mode [api|account|status]；配置路径可由 AI_DESKTOP_MODE_CONFIG 指定')
        return
    settings = load_settings(client)
    if not mode:
        print('1) API 模式\n2) 账号模式\n3) 状态\nq) 退出')
        selection = input('> ').strip()
        if selection == 'q':
            return
        mode = {'1': 'api', '2': 'account', '3': 'status'}.get(selection, selection)
    if mode == 'status':
        print('客户端：' + settings['app'])
        for selected in ('api', 'account'):
            print(selected + ' 代理：' + ('已配置' if settings.get(selected + '_proxy') else '直连'))
    elif mode in ('api', 'account'):
        launch(client, settings, mode)
    else:
        raise ValueError('模式应为 api、account 或 status')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print('错误：' + str(error), file=sys.stderr)
        sys.exit(1)
