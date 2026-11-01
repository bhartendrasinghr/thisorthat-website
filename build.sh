#!/bin/sh
# What Vercel runs. This exists rather than living in vercel.json because
# buildCommand there is capped at 256 characters, and the install needs more
# than that to be done safely and to report itself.
#
# Two refresh steps in build.py need libraries that are not in the standard
# library: xlrd reads AMFI's .xls monthly report, pypdf reads the SIP table
# out of the monthly note. Both are pure Python and install in a second.
#
# The install has to go into the SAME interpreter that runs build.py below.
# An earlier version used whichever pip or uv happened to be on PATH; it
# reported success and build.py still could not import xlrd, because uv's
# --system target is not this python3. Hence python3 -m pip.
#
# Vercel's Python is uv-managed and refuses a plain install with
# "externally-managed-environment", so --break-system-packages is the
# supported way in; the second line is the fallback for an image without
# that restriction.

python3 -m pip install --quiet --break-system-packages xlrd pypdf 2>/dev/null \
  || python3 -m pip install --quiet xlrd pypdf 2>/dev/null \
  || true

# Say which it was, every build. A silent install that quietly did nothing is
# how this site served a three-week-stale page behind a green deploy once.
if python3 -c "import xlrd, pypdf" 2>/dev/null; then
  echo "AMFI parsers ready: the MF Pulse figures will refresh from source"
else
  echo "AMFI PARSERS MISSING: the MF Pulse step will skip and the committed"
  echo "mf-pulse-data.json will be served, carrying its own as-of date."
fi

# Never fail the deploy over a data refresh. A page that is a day stale and
# says so beats a site that will not build.
python3 build.py || true
