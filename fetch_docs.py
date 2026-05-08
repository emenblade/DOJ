"""
Fetches the Google Drive folder contents and categorizes documents into:
  - sop: the main Standard Operating Procedure document
  - updates: [LCRP] SC-DOJ XXX numbered directives (sorted newest first)
  - templates: everything else (sorted alphabetically)

Requires env var: GOOGLE_API_KEY
Reads: config.json
Writes: documents.json
"""

import json
import os
import re
import sys
import requests

def load_config():
    with open('config.json', encoding='utf-8') as f:
        return json.load(f)

def list_drive_folder(folder_id, api_key):
    url = 'https://www.googleapis.com/drive/v3/files'
    files = []
    page_token = None
    while True:
        params = {
            'q': f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
            'fields': 'nextPageToken,files(id,name,mimeType)',
            'pageSize': 1000,
            'key': api_key,
        }
        if page_token:
            params['pageToken'] = page_token
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        files.extend(data.get('files', []))
        page_token = data.get('nextPageToken')
        if not page_token:
            break
    return files

def doc_url(file_id, mime_type):
    if mime_type == 'application/vnd.google-apps.spreadsheet':
        return f'https://docs.google.com/spreadsheets/d/{file_id}/edit'
    if mime_type == 'application/vnd.google-apps.presentation':
        return f'https://docs.google.com/presentation/d/{file_id}/edit'
    return f'https://docs.google.com/document/d/{file_id}/edit'

def categorize(files, config):
    update_re = re.compile(config.get('updatePattern', r'^\[LCRP\]\s+SC-DOJ\s+(\d{3})(.*)'), re.IGNORECASE)
    sop_re    = re.compile(config.get('sopPattern', r'standard operating procedure|\bS\.?O\.?P\.?\b'), re.IGNORECASE)

    result = {'sop': None, 'updates': [], 'templates': []}

    for f in files:
        name = f['name']
        url  = doc_url(f['id'], f.get('mimeType', ''))
        entry = {'id': f['id'], 'name': name, 'url': url}

        update_match = update_re.match(name)
        if update_match:
            number = int(update_match.group(1))
            remainder = update_match.group(2).strip() if update_match.lastindex >= 2 else ''
            remainder = remainder.lstrip(' —-:–').strip()
            entry['number'] = number
            entry['displayName'] = remainder if remainder else f'SC-DOJ {number:03d}'
            result['updates'].append(entry)
        elif sop_re.search(name):
            result['sop'] = entry
        else:
            result['templates'].append(entry)

    result['updates'].sort(key=lambda x: x['number'], reverse=True)
    result['templates'].sort(key=lambda x: x['name'].lower())
    return result

def main():
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print('ERROR: GOOGLE_API_KEY environment variable not set.', file=sys.stderr)
        sys.exit(1)

    config = load_config()
    folder_id = config.get('folderId')
    if not folder_id:
        print('ERROR: folderId not set in config.json.', file=sys.stderr)
        sys.exit(1)

    print(f'Fetching folder: {folder_id}')
    files = list_drive_folder(folder_id, api_key)
    print(f'Found {len(files)} files')

    result = categorize(files, config)
    print(f'  SOP:       {"found" if result["sop"] else "not found"}')
    print(f'  Updates:   {len(result["updates"])}')
    print(f'  Templates: {len(result["templates"])}')

    with open('documents.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print('Written: documents.json')

if __name__ == '__main__':
    main()
