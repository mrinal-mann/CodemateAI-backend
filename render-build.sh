#!/usr/bin/env bash
set -e  # Exit on error
set -x  # Print commands

echo "================================================"
echo "Starting CodeMate AI Build Process"
echo "================================================"

# Step 1: Upgrade pip
echo ">>> Step 1: Upgrading pip..."
pip install --upgrade pip

# Step 2: Install dependencies
echo ">>> Step 2: Installing Python dependencies..."
pip install -r requirements.txt

# Step 3: Ensure Prisma binary platform
echo ">>> Step 3: Setting Prisma binary platform..."
export PRISMA_BINARY_PLATFORM="debian-openssl-3.0.x"

# Step 4: Fetch Prisma binaries
echo ">>> Step 4: Fetching Prisma query engine..."
python -c "
from prisma.cli import prisma
prisma(['py', 'fetch'])
"

# Alternative fetch method
prisma py fetch || echo "Warning: prisma py fetch failed, trying alternative..."

# Step 5: Generate Prisma client
echo ">>> Step 5: Generating Prisma client..."
prisma generate --schema=prisma/schema.prisma

# Step 6: Verify Prisma setup
echo ">>> Step 6: Verifying Prisma installation..."
python -c "
try:
    from prisma import Prisma
    print('✅ Prisma client import successful')
except Exception as e:
    print(f'❌ Prisma client import failed: {e}')
    exit(1)
"

echo "================================================"
echo "✅ Build completed successfully!"
echo "================================================"