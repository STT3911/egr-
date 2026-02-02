-- Add search_name column to egr_company_names_history if missing (for normalized search)
ALTER TABLE egr_company_names_history
ADD COLUMN IF NOT EXISTS search_name TEXT;
