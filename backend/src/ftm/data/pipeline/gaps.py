"""Pipeline step: gaps. Owner: M3.

Must return processed values with flags and a ProcessingStep (name, params, affected_count, reason)
so the Data Journey can show what changed and why. See DEVELOPMENT_GUIDE.md section 6.
"""

# Rules: missing rainfall is NOT zero and is not interpolated by default. Short gaps in continuous
# variables may be estimated only with a declared max gap + method, and flagged as estimated.
