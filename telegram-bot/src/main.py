import logging
import boto3
import botocore
import json
import requests
import os
import sys
from uuid import uuid4
from typing import Dict
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply
)
from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)
from project_config import (
    handlers,
    preference_options,
    preference_data,
    numeric_cols,
    display_order,
    TIME_INTERVAL
)

LAMBDA_FUNCTION = os.environ.get('LAMBDA_FUNCTION')
API_URI = os.environ.get('API_URI')
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
mode = os.environ.get('MODE')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if mode == 'dev':
    def run(application):
        application.run_polling()

elif mode == 'prod':
    def run(application):
        PORT = int(os.environ.get('PORT', 80))
        HEROKU_APP_NAME = os.environ.get('HEROKU_APP_NAME')
        application.run_webhook(
            listen='0.0.0.0',
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f'https://{HEROKU_APP_NAME}.herokuapp.com/{BOT_TOKEN}'
        )

else:
    logging.error('No mode specified!')
    sys.exit(1)


preference_key_count = 0
new_preference = None
previous_updated_key = None
GET_NEW_PREFERENCE, GET_NUMERIC_INPUT = range(2)
UPDATE_CURRENT_PREFERENCE, CHOOSE_OPTION_TO_UPDATE, UPDATE_NUMERIC_SELECTION = range(2, 5)
DELETE_PREFERENCE = 5


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f'Hello {update.message.chat.first_name},\n' + \
        'Property Towkay is here to help you find your next dream home!\n\n'
    text += 'Here are the commands that you can run:\n\n'
    for handle, description in handlers.items():
        text += f'{handle}: {description}\n'
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text
    )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = 'Here are the commands that you can run:\n\n'
    for handle, description in handlers.items():
        text += f'{handle}: {description}\n'
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I didn't understand that command.",
    )


async def create_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # check for existing preference
    preference = await get_existing_preference(update, context)
    if preference:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Existing preference exists, please delete it first'
        )
        return ConversationHandler.END
    # user inputs a new preference
    buttons = [
        [
            InlineKeyboardButton('Yes', callback_data='Yes'),
            InlineKeyboardButton('No', callback_data='No')
        ]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='No existing preference, would you like to create a new preference?',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    global new_preference
    new_preference = preference_data.copy()
    new_preference['user_id'] = update.message.from_user.id
    return GET_NEW_PREFERENCE


async def get_existing_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = requests.get(f'{API_URI}/{update.message.from_user.id}')
    if r.status_code == 404:
        return
    return r.json()


async def read_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preference = await get_existing_preference(update, context)
    if not preference:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='No existing preference found, please create one first'
        )
        return
    text = 'Preference found:\n\n'
    for col in display_order:
        key = ' '.join(col.split('_'))
        text += f"{key}: {preference.get(col, '')}\n"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text
    )
    return preference


async def delete_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preference = await read_preference(update, context)
    if not preference:
        return
    buttons = [
        [
            InlineKeyboardButton('Yes', callback_data='Yes'),
            InlineKeyboardButton('No', callback_data='No')
        ]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Are you sure you want to delete these preferences?',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return DELETE_PREFERENCE


async def delete_preference_actual(update: Update, context: CallbackContext):
    query = update.callback_query.data
    await update.callback_query.answer()
    if query == 'No':
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Ending current operation...'
        )
        return ConversationHandler.END
    r = requests.delete(f'{API_URI}/{update.callback_query.from_user.id}')
    if r.status_code == 400:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Deletion failed...'
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Deletion successful...'
        )
    return ConversationHandler.END

async def get_new_preference(update: Update, context: CallbackContext):
    global preference_key_count, new_preference
    last_key = list(preference_options.keys())[preference_key_count - 1]
    if not preference_options[last_key]:
        query = update.message.text
    else:
        query = update.callback_query.data
        await update.callback_query.answer()
    if query == 'No':
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Ending current operation...'
        )
        return ConversationHandler.END
    if preference_key_count > 0:
        if last_key in numeric_cols:
            try:
                query = int(query)
                if query > 0:
                    new_preference[last_key] = query
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text='Invalid input added, please type a positive number...'
                    )
                    preference_key_count -= 1
            except:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='Invalid input added, please type a number...'
                )
                preference_key_count -= 1
        elif last_key == 'district':
            new_preference[last_key] = query.split(' ')[0]
        else:
            new_preference[last_key] = query
        if preference_key_count == len(preference_options.keys()):
            preference_key_count = 0
            create_success = await post_preference(new_preference)
            if not create_success:
                text = 'Error saving preference...'
            else:
                text = 'Successfully created preference!\n\n'
                for col in display_order:
                    key = ' '.join(col.split('_'))
                    text += f"{key}: {new_preference.get(col, '')}\n"
                text += '\nType /schedule_scraper to run your scraper'
            new_preference = preference_data.copy()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text
            )
            return ConversationHandler.END
    category = list(preference_options.keys())[preference_key_count]
    preference_key_count += 1
    text = 'Choose - ' + ' '.join(category.split('_')).lower() + '\n'
    text += 'Type /cancel to stop current operation\n\n'
    if category == 'property_type_code':
        options = preference_options[category][new_preference.get('property_type')]
    else:
        options = preference_options[category]
    if not options:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=ForceReply(True)
        )
        return GET_NUMERIC_INPUT
    else:
        buttons = []
        for i, option in enumerate(options):
            text += f'{i + 1}. {option}\n'
            buttons.append([
                InlineKeyboardButton(
                    text=option,
                    callback_data=option
                )
            ])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    return GET_NEW_PREFERENCE


async def schedule_scraper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # get frequency from db
    preference = await read_preference(update, context)
    if not preference:
        return
    frequency = int(preference.get('job_frequency_hours', -1))
    if frequency == -1:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text='Error with previous preference, please create new preference'
        )
        return
    chat_id = update.effective_message.chat_id
    jobs_removed = remove_job_if_exists(str(chat_id), context)
    context.job_queue.run_repeating(
        callback=invoke_scraper,
        interval=TIME_INTERVAL*frequency,
        data=json.dumps(preference),
        chat_id=update.effective_message.chat_id,
        first=0,
        name=str(chat_id)
    )
    text = ''
    if jobs_removed:
        text += 'Cleared job queue...\n\n'
    text += f'Scraping scheduled for every {frequency} hour(s) for the above preferences\n' + \
        'Type /stop_scraper to stop the scraping process at any time'
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=text
    )


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def stop_scraper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs_removed = remove_job_if_exists(str(update.effective_message.chat_id), context)
    if jobs_removed:
        text = 'Pending job removed successfully, scraping stopped...'
    else:
        text = 'No pending job to remove...'
    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=text
    )


async def invoke_scraper(context: CallbackContext):
    config = botocore.config.Config(
        read_timeout=900,
        connect_timeout=900,
        retries={"max_attempts": 0}
    )
    session = boto3.Session()
    lambda_client = session.client(
        service_name='lambda',
        region_name='ap-southeast-1',
        config=config,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )
    invoke_response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION,
        InvocationType='RequestResponse',
        Payload=context.job.data
    )
    response = json.loads(invoke_response['Payload'].read())
    if response['statusCode'] == 500:
        text = 'An error occurred when running scraper...'
    else:
        links = json.loads(response['body'])
        if not links:
            text = 'No new listings found\n'
        else:
            text = 'New listings found!\n'
            for link in links:
                text += f'\n{link[0]}\n{link[1]}\n'
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=text
    )


async def post_preference(new_preference: Dict) -> bool:
    r = requests.post(API_URI, json=new_preference)
    if r.status_code in [400, 500]:
        return False
    return True


async def put_preference(payload: Dict) -> bool:
    r = requests.put(f"{API_URI}/{payload['user_id']}", json=payload)
    if r.status_code == 400:
        return False
    return True


async def update_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preference = await read_preference(update, context)
    if not preference:
        return
    buttons = [
        [
            InlineKeyboardButton('Yes', callback_data='Yes'),
            InlineKeyboardButton('No', callback_data='No')
        ]
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text='Would you like to update your preferences?',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    global new_preference
    new_preference = preference.copy()
    return UPDATE_CURRENT_PREFERENCE


async def update_current_preference(update: Update, context: CallbackContext):
    global previous_updated_key, new_preference
    if previous_updated_key and not preference_options[previous_updated_key]:
        query = update.message.text
    else:
        query = update.callback_query.data
        await update.callback_query.answer()
    if not previous_updated_key:
        if query == 'No':
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='Ending current operation...'
            )
            return ConversationHandler.END
    if previous_updated_key in numeric_cols:
        try:
            query = int(query)
            if query > 0:
                    new_preference[previous_updated_key] = query
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='Invalid input added, please type a positive number...'
                )
        except:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text='Invalid input added, please type a number...'
            )
    elif previous_updated_key == 'district':
        new_preference[previous_updated_key] = query.split(' ')[0]
    elif previous_updated_key:
        new_preference[previous_updated_key] = query
    text = 'Current preference:\n\n'
    for col in display_order:
        key = ' '.join(col.split('_'))
        text += f"{key}: {new_preference.get(col, '')}\n"
    text += '\nWhich category would you like to update?\n'
    text += '(Select Submit to submit your updates or Cancel to exit)'
    buttons = []
    for col in display_order:
        category = ' '.join(col.split('_'))
        buttons.append([
            InlineKeyboardButton(
                text=category,
                callback_data=col
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text='Submit',
            callback_data='Submit'
        ),
        InlineKeyboardButton(
            text='Cancel',
            callback_data='Cancel'
        )
    ])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSE_OPTION_TO_UPDATE


async def choose_option_to_update(update: Update, context: CallbackContext):
    global previous_updated_key, new_preference
    query = update.callback_query.data
    await update.callback_query.answer()
    if query == 'Cancel':
        new_preference = preference_data.copy()
        previous_updated_key = None
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Ending current operation...'
        )
        return ConversationHandler.END
    if query == 'Submit':
        # update preference
        for col in numeric_cols:
            new_preference[col] = int(new_preference[col])
        update_success = await put_preference(new_preference)
        if not update_success:
            text = 'Error updating preferences...'
        else:
            text = 'Successfully updated preferences!\n\n'
            for col in display_order:
                key = ' '.join(col.split('_'))
                text += f"{key}: {new_preference.get(col, '')}\n"
            text += '\nType /schedule_scraper to run your scraper'
        new_preference = preference_data.copy()
        previous_updated_key = None
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text
        )
        return ConversationHandler.END
    previous_updated_key = query
    category = ' '.join(query.split('_'))
    text = 'Choose - ' + category + '\n'
    text += 'Type /cancel to stop current operation\n\n'
    if query == 'property_type_code':
        options = preference_options[query][new_preference.get('property_type')]
    else:
        options = preference_options[query]
    if not options:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=ForceReply(True)
        )
        return UPDATE_NUMERIC_SELECTION
    buttons = []
    for i, option in enumerate(options):
        text += f'{i + 1}. {option}\n'
        buttons.append([
            InlineKeyboardButton(
                text=option,
                callback_data=option
            )
        ])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return UPDATE_CURRENT_PREFERENCE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global new_preference, preference_key_count, previous_updated_key
    new_preference = None
    previous_updated_key = None
    preference_key_count = 0
    await update.message.reply_text('Operation cancelled...')
    return ConversationHandler.END


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', help)
    scraper_handler = CommandHandler('schedule_scraper', schedule_scraper)
    stop_scraper_handler = CommandHandler('stop_scraper', stop_scraper)
    read_handler = CommandHandler('read', read_preference)
    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    delete_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', delete_preference)],
        states={
            DELETE_PREFERENCE: [
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(callback=delete_preference_actual)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    create_handler = ConversationHandler(
        entry_points=[CommandHandler('create', create_preference)],
        states={
            GET_NEW_PREFERENCE: [
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(callback=get_new_preference)
            ],
            GET_NUMERIC_INPUT: [
                CommandHandler('cancel', cancel),
                MessageHandler(
                    filters=(filters.TEXT & ~filters.COMMAND),
                    callback=get_new_preference
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    update_handler = ConversationHandler(
        entry_points=[CommandHandler('update', update_preference)],
        states={
            UPDATE_CURRENT_PREFERENCE: [
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(callback=update_current_preference)
            ],
            CHOOSE_OPTION_TO_UPDATE: [
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(callback=choose_option_to_update)
            ],
            UPDATE_NUMERIC_SELECTION: [
                CommandHandler('cancel', cancel),
                MessageHandler(
                    filters=(filters.TEXT & ~filters.COMMAND),
                    callback=update_current_preference
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(scraper_handler)
    application.add_handler(stop_scraper_handler)
    application.add_handler(delete_handler)
    application.add_handler(read_handler)
    application.add_handler(create_handler)
    application.add_handler(update_handler)
    application.add_handler(unknown_handler)

    run(application)
