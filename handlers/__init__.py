from . import (
    common_handlers,
    settings_handler,
    request_handler,
    games_admin_handler,
    games_user_handler,
    packages_admin_handler,
    packages_user_handler,
    transaction_handler,
    system_settings_handler,
    purchase_handler,
    user_profile_handler,
    broadcast_handler,
    referral_handler,
    commands_handler,
)

# Create a list of all routers for easy inclusion
all_routers = [
    common_handlers.router,
    request_handler.router,
    settings_handler.router,
    games_admin_handler.router,
    packages_admin_handler.router,
    games_user_handler.router,
    packages_user_handler.router,
    transaction_handler.router,
    system_settings_handler.router,
    purchase_handler.router,
    user_profile_handler.router,
    broadcast_handler.router,
    referral_handler.router,
    commands_handler.router,
]
