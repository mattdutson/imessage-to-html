#!/usr/bin/env python3

import html
import os
import os.path as path
import sqlite3
import shutil
from datetime import datetime, timedelta, timezone

OUTPUT_FILENAME = path.join('.', 'output.html')
ATTACHMENTS_DIR = path.join('.', 'attachments')
DB_PATH = path.join(path.expanduser('~'), 'Library', 'Messages', 'chat.db')
HTML_HEAD = '<html>\n<head>\n<meta charset="utf-8"/>\n</head>\n<body>\n'
HTML_TAIL = '</body>\n</html>'


def wildcards(items):
    return ','.join(['?'] * len(items))


def unpack_column(results):
    unpacked = []
    for item in results:
        unpacked.append(item[0])
    return unpacked


def get_handle_ids(db):
    user_ids_raw = input(
        'Enter a comma-separated list of user IDs to search for. In '
        'general, the user ID is either a phone number with country '
        'code and no spaces (e.g., "+15554443333") or an email address.'
        '\nUser IDs: ')
    user_ids = list(map(str.strip, user_ids_raw.split(',')))
    db.execute('''
        SELECT ROWID
        FROM handle
        WHERE id IN ({})
        '''.format(wildcards(user_ids)), user_ids)
    handle_ids = unpack_column(db.fetchall())
    if not handle_ids:
        exit('Error: Unable to locate any of the specified users.')
    return handle_ids


def get_chat_ids(db, handle_ids):
    db.execute('''
        SELECT DISTINCT chat_id
        FROM chat_handle_join
        WHERE handle_id IN ({})
        '''.format(wildcards(handle_ids)), handle_ids)
    all_chat_ids = unpack_column(db.fetchall())

    if len(all_chat_ids) > 1:
        print('Multiple chats found containing the specified user IDs:')
        pad_width = len(str(len(all_chat_ids) + 1))
        for i, chat_id in enumerate(all_chat_ids):
            db.execute('''
                SELECT handle.id
                FROM handle
                INNER JOIN chat_handle_join
                ON handle.ROWID = chat_handle_join.handle_id
                WHERE chat_handle_join.chat_id = ?
                ''', (chat_id,))
            handle_ids = unpack_column(db.fetchall())
            padded = str(i + 1).rjust(pad_width)
            print('    Option {}:  {}'.format(padded, ', '.join(handle_ids)))
        indices_raw = input('Enter a comma-selected list of chats (e.g., "2,3,17"): ')

        chat_ids = []
        for index_raw in indices_raw.split(','):
            try:
                index = int(index_raw)
                if index < 1 or index > len(all_chat_ids):
                    exit('Error: "{}" is not an available option.'.format(index))
                chat_ids.append(all_chat_ids[index - 1])
            except ValueError:
                exit('Error: "{}" is not a valid integer.'.format(index_raw))
        return chat_ids

    else:
        return all_chat_ids


def retrieve_messages(db, chat_ids):
    db.execute('''
        SELECT 
            message.text,
            message.date,
            message.is_from_me,
            handle.id,
            attachment.filename
        FROM message
        INNER JOIN chat_message_join
        ON message.ROWID = chat_message_join.message_id
        LEFT JOIN handle
        ON message.handle_id = handle.ROWID
        LEFT JOIN message_attachment_join
        ON message.ROWID = message_attachment_join.message_id
        LEFT JOIN attachment
        ON attachment.ROWID = message_attachment_join.attachment_id
        WHERE chat_id IN ({})
        ORDER BY message.date
        '''.format(wildcards(chat_ids)), chat_ids)
    return db.fetchall()


def get_int(message, none_ok=False):
    selection = input(message)
    if selection.strip() == '' and none_ok:
        return None
    try:
        return int(selection)
    except ValueError:
        exit('Error: "{}" is not a valid integer.'.format(selection))


def get_year():
    return get_int('Enter a year (or press enter for all years): ', none_ok=True)


def get_month():
    month = get_int('Enter a month as an integer (or press enter for all months): ', none_ok=True)
    if month and (month < 1 or month > 12):
        exit('Error: "{}" is not a valid month.'.format(month))
    return month


def get_utc_offset():
    return get_int('Enter a UTC offset in hours: ')


def prepare_messages(messages, year, month, utc_offset):
    prepared = []
    for message in messages:
        text, nanoseconds, is_from_me, user_id, attachment_filename = message
        stamp = (datetime(2001, 1, 1, tzinfo=timezone.utc)
                 + timedelta(hours=utc_offset)
                 + timedelta(seconds=nanoseconds / 1000000000))
        if year is not None and stamp.year != year:
            continue
        if month is not None and stamp.month != month:
            continue
        prepared.append((text, stamp, is_from_me, user_id, attachment_filename))
    return prepared


def write_messages(messages):
    os.makedirs(ATTACHMENTS_DIR)

    my_name = input('Enter your name: ')
    other_names = {}

    with open(OUTPUT_FILENAME, 'w') as file:
        file.write(HTML_HEAD)
        last_day = None
        attachment_id = 0
        for message in messages:
            text, stamp, is_from_me, user_id, attachment = message
            if stamp.day != last_day:
                date_str = stamp.strftime('%A, %B %d, %Y')
                file.write('<h2>{}</h2>\n'.format(date_str))
                last_day = stamp.day
            align = 'left' if is_from_me else 'right'
            file.write('<p style="text-align:{}">\n'.format(align))
            if attachment is not None:
                ext = path.splitext(attachment)[-1]
                if ext != '.pluginPayloadAttachment':
                    dst_path = path.join(ATTACHMENTS_DIR, str(attachment_id) + ext)
                    try:
                        shutil.copyfile(path.expanduser(attachment), dst_path)
                        escaped = html.escape(dst_path, quote=True)
                        file.write('<a href="{}">Attachment</a><br>\n'.format(escaped))
                        attachment_id += 1
                    except FileNotFoundError:
                        file.write('ATTACHMENT NOT FOUND.<br>')
            if text and (ord(text[0]) != 65532 or attachment is None):
                file.write('{}<br>\n'.format(html.escape(text)))
            if is_from_me or user_id is None:
                name = my_name
            elif user_id in other_names.keys():
                name = other_names[user_id]
            else:
                name = input('Enter a name for user "{}": '.format(user_id))
                other_names[user_id] = name
            file.write('<small>{}</small><br>\n'.format(html.escape(name)))
            stamp_str = stamp.strftime('%I:%M:%S %p')
            file.write('<small>{}</small><br>\n</p>'.format(stamp_str))
        file.write(HTML_TAIL)
    print('Done.')


def main():
    prevent_overwrite()
    db = sqlite3.connect(DB_PATH).cursor()
    handle_ids = get_handle_ids(db)
    chat_ids = get_chat_ids(db, handle_ids)
    messages = retrieve_messages(db, chat_ids)
    year = get_year()
    month = None if year is None else get_month()
    utc_offset = get_utc_offset()
    messages = prepare_messages(messages, year, month, utc_offset)
    write_messages(messages)


def prevent_overwrite():
    if path.exists(OUTPUT_FILENAME):
        exit('Error: Output file "{}" already exists. Delete or move it '
             'to proceed.'.format(OUTPUT_FILENAME))
    if path.exists(ATTACHMENTS_DIR):
        exit('Error: Attachment folder "{}" already exists. Delete or '
             'move it to proceed.'.format(ATTACHMENTS_DIR))


if __name__ == '__main__':
    main()
