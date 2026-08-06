# Integration note: ConnectionManager now supports registering additional
# services (e.g., adapters like TelegramAdapter) so lifecycle is managed
# centrally. Use ConnectionManager.register_service() to add adapters before
# calling start().
