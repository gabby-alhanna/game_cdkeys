import os
import asyncpg
from dotenv import load_dotenv
import ssl

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Initializes the connection pool using .env credentials."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.pool = await asyncpg.create_pool(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST", "127.0.0.1"),
            ssl=ctx,
            # Recommended for asyncpg to handle UUIDs and JSON easily
            min_size=1,
            max_size=10
        )
        print("✅ PostgreSQL Connection Pool Established")

    async def create_tables(self):
        """Refined schema: User claims code -> Admin verifies and charges."""
        setup_query = """
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

        -- 1. System Settings (SuperAdmin Identity & Payment Info)
        CREATE TABLE IF NOT EXISTS system_settings (
            id SERIAL PRIMARY KEY,
            superadmin_shamcash_code TEXT,
            superadmin_qr_file_id TEXT, 
            last_updated TIMESTAMP DEFAULT NOW()
        );

        -- 2. Users Table
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            chat_id BIGINT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            balance DECIMAL(15, 2) DEFAULT 0.00 CHECK (balance >= 0),
            is_superadmin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 3. Balance Requests (The claim ticket)
        CREATE TABLE IF NOT EXISTS balance_requests (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            transfer_code TEXT UNIQUE NOT NULL, 
            description TEXT,                   
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 4. Games & Packages
        CREATE TABLE IF NOT EXISTS games (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name TEXT NOT NULL UNIQUE,
            image_file_id TEXT,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS game_packages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            game_id UUID REFERENCES games(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            price DECIMAL(15, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 5. Final Transactions
        CREATE TABLE IF NOT EXISTS transactions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id),
            amount DECIMAL(15, 2) NOT NULL,
            type TEXT CHECK (type IN ('charge', 'purchase', 'adjustment')),
            description TEXT,              
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        -- 6. For Buttons
        CREATE TABLE IF NOT EXISTS reply_buttons (
            button_key TEXT PRIMARY KEY,
            display_text TEXT NOT NULL,
            image_file_id TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS purchase_requests (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            game_id UUID REFERENCES games(id) ON DELETE CASCADE,
            package_id UUID REFERENCES game_packages(id) ON DELETE CASCADE,
            game_account_id TEXT NOT NULL,
            price DECIMAL(15,2) NOT NULL,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT NOW()
        );
        """
        async with self.pool.acquire() as conn:
            await conn.execute(setup_query)
            # Seed system settings if empty
            if not await conn.fetchval("SELECT 1 FROM system_settings WHERE id = 1"):
                await conn.execute("INSERT INTO system_settings (id) VALUES (1)")
        
        count = await self.fetchval("SELECT COUNT(*) FROM reply_buttons")
        if count == 0:
            defaults = [
                ('main', '🏠 Main', None, 'Main menu placeholder'),
                ('help', '❓ Help', None, '🆘 **Help**\n\nUse the buttons below to navigate.'),
                ('about', 'ℹ️ About', None, 'ℹ️ **About This Bot**\n\nVersion 1.0')
            ]
            for key, text, img, desc in defaults:
                await self.execute(
                    "INSERT INTO reply_buttons (button_key, display_text, image_file_id, description) VALUES ($1, $2, $3, $4)",
                    key, text, img, desc
                )
                
    async def execute(self, query, *args):
        """For INSERT, UPDATE, DELETE."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query, *args):
        """For SELECTing multiple rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query, *args):
        """For SELECTing a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query, *args):
        """For getting a single value (like a COUNT or a specific ID)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def close(self):
        """Gracefully close the pool."""
        await self.pool.close()

# Create a single instance to be imported elsewhere
db = DatabaseManager()