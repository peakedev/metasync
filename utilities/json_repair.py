#!/usr/bin/env python3
"""
JSON Repair Utilities

This module provides independent functions to repair common JSON issues
in LLM responses. Each function handles a specific type of repair.
"""

import re
import json
from typing import Optional


def remove_markdown_code_blocks(json_string: str) -> str:
    """
    Remove markdown code blocks from JSON string.
    
    Args:
        json_string: Raw JSON string that may be wrapped in markdown
        
    Returns:
        Cleaned JSON string without markdown wrappers
    """
    cleaned = json_string.strip()
    
    if cleaned.startswith('```'):
        # Remove opening ```json or ```
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.MULTILINE)
        # Remove closing ```
        cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
    
    return cleaned


def fix_trailing_commas(json_string: str) -> str:
    """
    Remove trailing commas in objects and arrays.
    
    Args:
        json_string: JSON string that may have trailing commas
        
    Returns:
        JSON string with trailing commas removed
    """
    # Fix trailing commas in objects and arrays
    return re.sub(r',(\s*[}\]])', r'\1', json_string)


def fix_missing_commas_between_structures(json_string: str) -> str:
    """
    Fix missing commas between objects and arrays.
    
    Args:
        json_string: JSON string that may be missing commas between structures
        
    Returns:
        JSON string with missing commas added
    """
    # Fix missing commas between fields (common LLM error)
    # Look for "} " followed by "{" or "]" followed by "["
    repaired = re.sub(r'}\s*{', '},{', json_string)
    repaired = re.sub(r']\s*\[', '],[', repaired)
    return repaired


def fix_missing_commas_between_strings(json_string: str) -> str:
    """
    Fix missing commas between string values.
    
    Args:
        json_string: JSON string that may be missing commas between string values
        
    Returns:
        JSON string with missing commas added
    """
    # Look for "string" followed by "string" (missing comma)
    return re.sub(r'"\s*"([^"]*)"\s*:', r'","\1":', json_string)


def fix_unescaped_quotes(json_string: str) -> str:
    """
    Convert unescaped double quotes to single quotes within JSON string values.
    
    Args:
        json_string: JSON string that may have unescaped quotes
        
    Returns:
        JSON string with unescaped quotes converted to single quotes
    """
    lines = json_string.split('\n')
    
    for i, line in enumerate(lines):
        # Look for lines that contain unescaped quotes inside string values
        # Pattern: "key": "content with "quotes" inside"
        if '": "' in line and line.count('"') > 4:  # More than 4 quotes suggests unescaped quotes inside
            # Find the key and value parts
            if ': "' in line:
                key_part, value_part = line.split(': "', 1)
                if value_part.count('"') > 1:  # Has quotes inside the value
                    # Convert unescaped double quotes to single quotes within the value
                    # Keep the opening and closing quotes as double quotes
                    # Find the last quote (closing quote) and preserve it
                    last_quote_pos = value_part.rfind('"')
                    if last_quote_pos > 0:
                        value_content = value_part[:last_quote_pos]  # Everything before the last quote
                        value_content = value_content.replace('"', "'")  # Convert internal quotes to single quotes
                        lines[i] = key_part + ': "' + value_content + '"'
    
    return '\n'.join(lines)


def fix_unescaped_quotes_in_html_attributes(json_string: str) -> str:
    """
    Fix unescaped quotes in HTML attributes within JSON string values.
    Specifically handles cases like href="url" within JSON string values.
    
    Args:
        json_string: JSON string that may have unescaped quotes in HTML attributes
        
    Returns:
        JSON string with properly escaped quotes in HTML attributes
    """
    import re
    
    # Simple approach: find and fix href="..." patterns directly
    # This handles the specific case where href="url" appears within JSON string values
    result = json_string
    
    # Fix href="..." patterns - use single quotes instead of escaped double quotes
    result = re.sub(r'href="([^"]*)"', r"href='\1'", result)
    result = re.sub(r'src="([^"]*)"', r"src='\1'", result)
    result = re.sub(r'alt="([^"]*)"', r"alt='\1'", result)
    result = re.sub(r'title="([^"]*)"', r"title='\1'", result)
    result = re.sub(r'class="([^"]*)"', r"class='\1'", result)
    result = re.sub(r'id="([^"]*)"', r"id='\1'", result)
    
    # Fix data-key='...' and data-variant='...' patterns - convert to double quotes
    result = re.sub(r"data-key='([^']*)'", r'data-key="\1"', result)
    result = re.sub(r"data-variant='([^']*)'", r'data-variant="\1"', result)
    
    return result


def fix_missing_commas_between_lines(json_string: str) -> str:
    """
    Fix missing commas between lines that should be connected.
    
    Args:
        json_string: JSON string that may be missing commas between lines
        
    Returns:
        JSON string with missing commas added between lines
    """
    lines = json_string.split('\n')
    
    for i, line in enumerate(lines):
        # Look for lines that end with " and next line starts with "
        if i < len(lines) - 1:
            if line.strip().endswith('"') and lines[i+1].strip().startswith('"'):
                # Add comma at end of current line
                lines[i] = line.rstrip() + ','
    
    return '\n'.join(lines)


def repair_json_comprehensive(json_string: str) -> str:
    """
    Apply all JSON repair functions in sequence.
    
    Args:
        json_string: Raw JSON string from LLM
        
    Returns:
        Repaired JSON string
    """
    print(" (LLM's JSON was fucked again. Attempting logic-based JSON repair")
    
    # Apply repairs in sequence
    repaired = remove_markdown_code_blocks(json_string)
    repaired = fix_trailing_commas(repaired)
    repaired = fix_missing_commas_between_structures(repaired)
    repaired = fix_missing_commas_between_strings(repaired)
    repaired = fix_unescaped_quotes_in_html_attributes(repaired)  # New function for HTML attributes
    repaired = fix_unescaped_quotes(repaired)
    repaired = fix_missing_commas_between_lines(repaired)
    
    # Don't print success here - let the caller validate and print the result
    return repaired


def validate_json(json_string: str) -> tuple[bool, Optional[str]]:
    """
    Validate if a JSON string is valid.
    
    Args:
        json_string: JSON string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        json.loads(json_string)
        return True, None
    except json.JSONDecodeError as e:
        return False, str(e)


def repair_and_validate(json_string: str) -> tuple[str, bool, Optional[str]]:
    """
    Repair JSON and validate the result.
    
    Args:
        json_string: Raw JSON string from LLM
        
    Returns:
        Tuple of (repaired_json, is_valid, error_message)
    """
    repaired = repair_json_comprehensive(json_string)
    is_valid, error = validate_json(repaired)
    return repaired, is_valid, error
