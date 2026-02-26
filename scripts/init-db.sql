-- Create test database if it doesn't exist
-- This runs on first container startup only

SELECT 'CREATE DATABASE vocabapp_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vocabapp_test')\gexec
