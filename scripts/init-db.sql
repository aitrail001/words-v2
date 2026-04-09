-- Create the persistent test database if it doesn't exist
-- This runs on first container startup only

SELECT 'CREATE DATABASE vocabapp_test_full'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vocabapp_test_full')\gexec

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
