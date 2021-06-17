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


def unpack_column(results):
    unpacked = []
    for item in results:
        unpacked.append(item[0])
    return unpacked


def get_handle_ids(db):
    user_id = input(
        'Enter a user ID to search for. In general, the user ID is the '
        'phone number with country code and no spaces (e.g., '
        '"+15554443333").\nUser ID: ')
    db.execute('''
        SELECT ROWID
        FROM handle
        WHERE id = ?
        ''', (user_id,))
    handle_ids = unpack_column(db.fetchall())
    if not handle_ids:
        exit('Error: Unable to locate a user with ID "{}".'.format(user_id))
    return handle_ids


def get_chat_id(db, handle_ids):
    wildcards = ','.join(['?'] * len(handle_ids))
    db.execute('''
        SELECT DISTINCT chat_id
        FROM chat_handle_join
        WHERE handle_id IN ({})
        '''.format(wildcards), handle_ids)
    chat_ids = unpack_column(db.fetchall())

    if len(chat_ids) > 1:
        print('Multiple chats found containing the specified user ID:')
        pad_width = len(str(len(chat_ids) + 1))
        for i, chat_id in enumerate(chat_ids):
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
        selection = input('Select a chat by entering its number: ')

        try:
            selection = int(selection)
        except ValueError:
            exit('Error: "{}" is not a valid integer.'.format(selection))
        if selection < 1 or selection > len(chat_ids):
            exit('Error: "{}" is not an available option.'.format(selection))
        return chat_ids[selection - 1]

    else:
        return chat_ids[0]


def retrieve_messages(db, chat_id):
    db.execute('''
        SELECT 
            message.text,
            message.handle_id,
            message.date,
            message.is_from_me,
            attachment.filename
        FROM message
        INNER JOIN chat_message_join
        ON message.ROWID = chat_message_join.message_id
        LEFT JOIN message_attachment_join
        ON message.ROWID = message_attachment_join.message_id
        LEFT JOIN attachment
        ON attachment.ROWID = message_attachment_join.attachment_id
        WHERE chat_id = ?
        ORDER BY message.date
        ''', (chat_id,))
    messages = db.fetchall()

    return messages


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


def get_my_name():
    return input('Enter your name: ')


def get_other_names(db, chat_id):
    db.execute('''
        SELECT handle.ROWID, handle.id
        FROM handle
        INNER JOIN chat_handle_join
        ON handle.ROWID = chat_handle_join.handle_id
        WHERE chat_handle_join.chat_id = ?
        ''', (chat_id,))
    results = db.fetchall()
    names = {}
    for row in results:
        handle_id, user_id = row
        name = input('Enter a name for user "{}": '.format(user_id))
        names[handle_id] = name
    return names


def prepare_messages(messages, year, month, utc_offset):
    prepared = []
    for message in messages:
        text, handle, nanoseconds, is_from_me, attachment_filename = message
        stamp = (datetime(2001, 1, 1, tzinfo=timezone.utc)
                 + timedelta(hours=utc_offset)
                 + timedelta(seconds=nanoseconds / 1000000000))
        if year is not None and stamp.year != year:
            continue
        if month is not None and stamp.month != month:
            continue
        prepared.append((text, handle, stamp, is_from_me, attachment_filename))
    return prepared


def write_messages(messages, my_name, other_names):
    print('Processing...')
    os.makedirs(ATTACHMENTS_DIR)

    with open(OUTPUT_FILENAME, 'w') as file:
        file.write(HTML_HEAD)
        last_day = None
        attachment_id = 0
        for message in messages:
            text, handle, stamp, is_from_me, attachment = message
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
                    shutil.copyfile(path.expanduser(attachment), dst_path)
                    escaped = html.escape(dst_path, quote=True)
                    file.write('<a href="{}">Attachment</a><br>\n'.format(escaped))
                    attachment_id += 1
            if text and (ord(text[0]) != 65532 or attachment is None):
                file.write('{}<br>\n'.format(html.escape(text)))
            if is_from_me or handle == 0:
                name = my_name
            else:
                name = other_names[handle]
            file.write('<small>{}</small><br>\n'.format(html.escape(name)))
            stamp_str = stamp.strftime('%I:%M:%S %p')
            file.write('<small>{}</small><br>\n</p>'.format(stamp_str))
        file.write(HTML_TAIL)
    print('Done.')


def main():
    prevent_overwrite()
    db = sqlite3.connect(DB_PATH).cursor()
    handle_ids = get_handle_ids(db)
    chat_id = get_chat_id(db, handle_ids)
    messages = retrieve_messages(db, chat_id)
    year = get_year()
    month = None if year is None else get_month()
    utc_offset = get_utc_offset()
    my_name = get_my_name()
    other_names = get_other_names(db, chat_id)
    messages = prepare_messages(messages, year, month, utc_offset)
    write_messages(messages, my_name, other_names)


def prevent_overwrite():
    if path.exists(OUTPUT_FILENAME):
        exit('Error: Output file "{}" already exists. Delete or move it '
             'to proceed.'.format(OUTPUT_FILENAME))
    if path.exists(ATTACHMENTS_DIR):
        exit('Error: Attachment folder "{}" already exists. Delete or '
             'move it to proceed.'.format(ATTACHMENTS_DIR))


if __name__ == '__main__':
    main()
