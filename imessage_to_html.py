#!/usr/bin/env python3

import os.path as path
import sqlite3
from argparse import ArgumentParser
from os.path import expanduser


def unpack_column(results):
    unpacked = []
    for item in results:
        unpacked.append(item[0])
    return unpacked


def find_handle_ids(db, user_id):
    db.execute(
        'SELECT ROWID FROM handle '
        'WHERE id = ?', (user_id,))
    handle_ids = unpack_column(db.fetchall())
    if not handle_ids:
        exit('Error: Unable to locate a user with ID "{}". In general, '
             'the user ID is the phone number with country code and '
             'no spaces. For example, "+15554443333".'.format(user_id))
    return handle_ids


def select_chat_id(db, handle_ids):
    wildcards = ','.join(['?'] * len(handle_ids))
    db.execute(
        'SELECT DISTINCT chat_id FROM chat_handle_join'
        'WHERE handle_id IN ({})'.format(wildcards), handle_ids)
    chat_ids = unpack_column(db.fetchall())
    if len(chat_ids) > 1:
        print('Multiple chats found containing the specified user ID:')
        pad_width = len(str(len(chat_ids) + 1))
        for i, chat_id in enumerate(chat_ids):
            db.execute(
                'SELECT handle.id '
                'FROM handle INNER JOIN chat_handle_join '
                'ON handle.ROWID = chat_handle_join.handle_id '
                'WHERE chat_message_join.chat_id = ?', (chat_id,))
            handle_ids = unpack_column(db.fetchall())
            padded = str(i + 1).rjust(pad_width)
            print('    Option {}:  {}'.format(padded, ', '.join(handle_ids)))
        selection = input('Select a chat by entering its number: ')

        try:
            selection = int(selection)
        except ValueError:
            exit('Error: "{}" is not a valid integer.'.format(selection))

        if selection < 0 or selection >= len(chat_ids):
            exit('Error: "{}" is not an available option.'.format(selection))
        return selection
    else:
        return chat_ids[0]


def retrieve_messages(db, chat_id):
    db.execute(
        'SELECT * '
        'FROM message INNER JOIN chat_message_join '
        'ON message.ROWID = chat_message_join.message_id '
        'WHERE chat_id = ?', (chat_id,))
    messages = db.fetchall()

    # TODO: Additional logic here

    return messages


def main(args):
    # Connect to the database.
    db_path = path.join(expanduser('~'), 'Library', 'Messages', 'chat.db')
    connection = sqlite3.connect(db_path)
    db = connection.cursor()

    # Retrieve a list of messages.
    handle_ids = find_handle_ids(db, args.user_id)
    chat_id = select_chat_id(db, handle_ids)
    messages = retrieve_messages(db, chat_id)


if __name__ == '__main__':
    parser = ArgumentParser()

    # TODO: Allow for multiple user IDs
    parser.add_argument(
        'user_id',
        help='the ID of one of the users on the message thread')

    main(parser.parse_args())
