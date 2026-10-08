# =============================================================================
# gam_config.py - "Edit gam.cfg" (2.86): GAM's settings file, for people who
# would rather not edit it by hand. Shared by the desktop app (GAMGUI.py)
# and the browser version (gam_web.py).
#
# How a change is saved (Gabe's choice): THROUGH GAM -
#   gam select <section> config <setting> <value> ... save
# so GAM itself checks every value and writes the file, and the command is
# shown first (it teaches the GAM way to do it). Checked with gam.exe
# 7.48.23 (10-08-2026) in a throwaway folder:
#   - 'config ... save' REWRITES gam.cfg: every setting is written out into
#     [DEFAULT] and COMMENTS ARE REMOVED (other sections are kept). So a
#     backup copy is saved first, every time, and the page says so.
#   - A bad value is refused ("Expected <integer 1<=x<=1000>"), exit code 2,
#     and the file is NOT changed.
#   - 'gam select <section> config verify [variables <regex>]' prints
#     "Section: <name>" then "  <setting> = <value>" ('' = blank).
# The expert page edits the file as text: backup first, a Python syntax
# check, then GAM reads it back ('config verify'); if GAM rejects it the
# backup can be put back.
#
# CFG_VARS holds FACTS about every setting from the GAM wiki's gam.cfg page
# (name, default, allowed values / range, environment variable) - generated
# by tests/gen_cfg_vars.py. The wiki's own descriptions are not copied; the
# page links to the wiki, and COMMON has GAMGUI's own plain words.
# =============================================================================

import configparser
import datetime
import os
import re
import shutil

WIKI_URL = "https://github.com/GAM-team/GAM/wiki/gam.cfg"

# The everyday settings for the simple page: (setting, label, help, kind,
# choices). kind: "bool" (Yes / No), "choice" (a dropdown; the value may
# also be typed when "free" is set), "int", "text", "folder". Help in our
# own words.
COMMON = [
    ("timezone", "Time zone for the times GAM shows",
     "utc = Google's own time; local = this computer's time zone; or a name "
     "such as America/Chicago.", "choice", ["utc", "local"], True),
    ("domain", "Your Google Workspace domain",
     "e.g. example.org - used when a command gives a name without @domain.",
     "text", None, False),
    ("customer_id", "Customer ID",
     "my_customer works for almost everyone; GAM fills in the real ID.",
     "text", None, False),
    ("admin_email", "Admin account GAM signs in as",
     "Blank = the account in oauth2.txt (set when GAM was authorized).",
     "text", None, False),
    ("num_threads", "Commands GAM runs at the same time (CSV / batch)",
     "1 to 1000. Higher is faster for big CSV files; Google may slow you "
     "down above about 20.", "int", None, False),
    ("drive_dir", "Folder for downloaded files",
     "Where GAM saves files when a command gives only a file name.",
     "folder", None, False),
    ("todrive_user", "Account that receives Google Sheet output",
     "Blank = the admin account.", "text", None, False),
    ("todrive_parent", "Drive folder for Google Sheet output",
     "root = the top of My Drive; or a folder ID / id:<ID> / name.",
     "text", None, False),
    ("todrive_timezone", "Time zone of new Google Sheets",
     "e.g. America/Chicago. Blank = Google's default for the account.",
     "text", None, False),
    ("todrive_noemail", "Do NOT email a link when a Google Sheet is made",
     "", "bool", None, False),
    ("todrive_nobrowser", "Do NOT open a new Google Sheet in a browser",
     "", "bool", None, False),
    ("no_browser", "Do NOT open a browser for sign-ins",
     "GAM prints the link instead - handy on a server.", "bool", None, False),
    ("show_gettings", "Show 'Getting ...' progress messages", "", "bool",
     None, False),
    ("csv_output_line_terminator", "Line endings in the CSV files GAM writes",
     "crlf = Windows (Excel, Notepad); lf = Mac / Linux.", "choice",
     ["lf", "crlf", "cr"], False),
    ("cmdlog", "GAM's own log of every command it runs",
     "A file path, e.g. C:\\GAMLogs\\gam.log. Blank = no log.", "text",
     None, False),
    ("no_verify_ssl", "Turn OFF the check of secure (SSL) connections",
     "Only when a web filter breaks GAM's connections - it makes GAM accept "
     "any certificate.", "bool", None, False),
]
COMMON_NAMES = [c[0] for c in COMMON]


def cfg_var(name):
    # The facts about one setting (CFG_VARS), or None.
    for var in CFG_VARS:
        if var["name"] == name:
            return var
    return None


def is_secret(name):
    var = cfg_var(name)
    return bool(var and var.get("secret")) or bool(re.search(r"password|secret", name))


def shown(name, value):
    # A value as it may be SHOWN (screen, preview, log): secrets masked.
    if is_secret(name) and value:
        return "********"
    return value


def section_word(section):
    # GAM's 'select' word for a section: 'default' for [DEFAULT].
    return "default" if not section or section.upper() == "DEFAULT" else section


def parse_verify(text):
    # 'gam select <s> config verify' output -> (section, {setting: value}).
    section, values = "", {}
    for line in (text or "").splitlines():
        found = re.match(r"^Section:\s*(.*)$", line.strip())
        if found:
            section = found.group(1).strip()
            continue
        found = re.match(r"^\s+([a-z][a-z0-9_]*)\s=\s?(.*)$", line)
        if found:
            value = found.group(2).strip()
            values[found.group(1)] = "" if value == "''" else value
    return section, values


def verify_command(section):
    return ["select", section_word(section), "config", "verify"]


def known_names(verify_values=None):
    # Every setting GAM knows. The live list from 'config verify' is the
    # truth (GAM 7.48.23 knows 139; the wiki lists 137 - it misses
    # enable_gcloud_reauth and no_update_check); the wiki facts otherwise.
    names = set(verify_values or ())
    return names or {var["name"] for var in CFG_VARS}


def save_command(section, changes, known=None):
    # changes: [(setting, new value)] -> the gam command (argument list).
    # ValueError for an unknown setting or 'section' (GAM refuses it).
    # known: the names GAM reported (known_names); default = the wiki list.
    known = known or known_names()
    argv = ["select", section_word(section), "config"]
    for name, value in changes:
        if name not in known or name == "section":
            raise ValueError("'%s' is not a gam.cfg setting GAMGUI can change." % name)
        argv += [name, value]
    return argv + ["save"]


def shown_command(argv):
    # The command for the preview / log: secrets masked.
    out, mask_next = [], False
    for word in argv:
        out.append("********" if mask_next and word else word)
        mask_next = is_secret(word)
    return out


def bool_value(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def changes_between(current, wanted):
    # The settings whose value differs: [(setting, new)] in COMMON / wanted
    # order. Yes / No settings compare as booleans (True == true).
    out = []
    for name, new in wanted:
        old = current.get(name, "")
        var = cfg_var(name) or {}
        if var.get("kind") == "bool":
            if bool_value(old) != bool_value(new):
                out.append((name, "true" if bool_value(new) else "false"))
        elif str(old) != str(new):
            out.append((name, new))
    return out


def gam_error(rc, output):
    # GAM's complaint about a config command in plain words, or "".
    found = re.search(r"ERROR:\s*(.*)", output or "")
    if found:
        return found.group(1).strip()
    if rc not in (0, None):
        tail = (output or "").strip().splitlines()
        return tail[-1] if tail else "GAM stopped with exit code %s" % rc
    return ""


def sections_in(text):
    # The section names in a gam.cfg text ("DEFAULT" first).
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    return ["DEFAULT"] + parser.sections()


def check_text(text, known=None):
    # A quick check of gam.cfg text before GAM reads it -> (error, warning).
    # error: the file cannot be read as a settings file (a missing [section]
    # line, a setting twice...) - do not save. warning: names GAM does not
    # know (usually a typo) - ask. known: known_names() (GAM's live list).
    known = known or known_names()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        return str(exc).splitlines()[0], ""
    unknown = sorted({key for sec in ["DEFAULT"] + parser.sections()
                      for key in parser[sec] if key not in known})
    if unknown:
        return "", ("GAM does not know these settings: " + ", ".join(unknown)
                    + " - check the spelling.")
    return "", ""


def backup(path):
    # A copy of gam.cfg next to it, never overwriting an older copy:
    # gam.cfg.backup-MM-DD-YYYY_HH-MM-SS[-2]. Returns its path.
    stamp = datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    base = path + ".backup-" + stamp
    target, number = base, 2
    while os.path.exists(target):
        target = "%s-%d" % (base, number)
        number += 1
    shutil.copy2(path, target)
    return target


def help_url(name):
    # The wiki page for a setting (GitHub turns the heading into an anchor
    # only for some pages, so the page itself).
    return WIKI_URL


# Generated by tests/gen_cfg_vars.py from the GAM wiki (10-08-2026) - facts only.
CFG_VARS = [{'name': 'activity_max_results', 'default': '100', 'range': '1 - 500', 'kind': 'int'},
 {'name': 'admin_email',
  'default': 'Blank, address from OAUTH2.TXT will be used',
  'env': 'GA_ADMIN_EMAIL',
  'kind': 'text'},
 {'name': 'api_calls_rate_check', 'default': 'False', 'kind': 'bool'},
 {'name': 'api_calls_rate_limit', 'default': '1000', 'range': '100 - Unlimited', 'kind': 'int'},
 {'name': 'api_calls_tries_limit', 'default': '10', 'range': '3-30', 'kind': 'int'},
 {'name': 'auto_batch_min',
  'default': "0, don't automatically generate gam batch commands",
  'range': '0 - 100',
  'env': 'GAM_AUTOBATCH',
  'kind': 'int'},
 {'name': 'bail_on_internal_error_tries', 'default': '2', 'range': '1 - 10', 'kind': 'int'},
 {'name': 'batch_size',
  'default': '50',
  'range': '1 - 1000',
  'env': 'GAM_BATCH_SIZE',
  'kind': 'int'},
 {'name': 'cacerts_pem',
  'default': 'Blank, internal cacerts.pem will be used',
  'env': 'GAM_CA_FILE',
  'kind': 'text'},
 {'name': 'cache_dir', 'default': '~/.gam/gamcache', 'env': 'GAMCACHEDIR', 'kind': 'text'},
 {'name': 'cache_discovery_only', 'signal': 'OldGamPath/allcache.txt', 'kind': 'bool'},
 {'name': 'channel_customer_id', 'default': 'Blank', 'kind': 'text'},
 {'name': 'charset', 'default': 'utf-8', 'env': 'GAM_CHARSET', 'kind': 'text'},
 {'name': 'chat_max_results', 'default': '100', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'classroom_max_results',
  'default': '0 (Google defined limit)',
  'range': '0 - 1000',
  'kind': 'int'},
 {'name': 'client_secrets_json',
  'default': '(the GAM config folder)/client_secrets.json',
  'env': 'CLIENTSECRETS',
  'kind': 'text',
  'secret': True},
 {'name': 'clock_skew_in_seconds', 'default': '10', 'range': '10 - 3600', 'kind': 'int'},
 {'name': 'cmdlog', 'default': "''", 'kind': 'text'},
 {'name': 'cmdlog_max_backups', 'default': '5', 'range': '1 - 10', 'kind': 'int'},
 {'name': 'cmdlog_max_kilo_bytes', 'default': '1000', 'range': '100 - 10000', 'kind': 'int'},
 {'name': 'commanddata_clientaccess', 'default': 'False', 'kind': 'bool'},
 {'name': 'config_dir', 'default': '~/.gam', 'env': 'GAMUSERCONFIGDIR', 'kind': 'text'},
 {'name': 'contact_max_results', 'default': '100', 'range': '1 - 10000', 'kind': 'int'},
 {'name': 'csv_input_column_delimiter', 'default': "','", 'kind': 'text'},
 {'name': 'csv_input_no_escape_char', 'default': 'True', 'kind': 'bool'},
 {'name': 'csv_input_quote_char', 'kind': 'text'},
 {'name': 'csv_input_row_drop_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_input_row_drop_filter_mode',
  'allowed': 'allmatch|anymatch',
  'default': "'anymatch'",
  'kind': 'choice'},
 {'name': 'csv_input_row_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_input_row_filter_mode',
  'allowed': 'allmatch|anymatch',
  'default': "'allmatch'",
  'kind': 'choice'},
 {'name': 'csv_input_row_limit', 'default': '0', 'kind': 'text'},
 {'name': 'csv_output_convert_cr_nl', 'default': 'False', 'kind': 'bool'},
 {'name': 'csv_output_column_delimiter', 'default': "','", 'kind': 'text'},
 {'name': 'csv_output_field_delimiter', 'default': "' '", 'kind': 'text'},
 {'name': 'csv_output_header_drop_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_header_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_header_force', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_header_order', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_header_required', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_line_terminator',
  'allowed': 'cr, lf, crlf',
  'default': 'lf',
  'kind': 'choice'},
 {'name': 'csv_output_no_escape_char', 'default': 'False', 'kind': 'bool'},
 {'name': 'csv_output_quote_char', 'default': '\'"\'', 'kind': 'text'},
 {'name': 'csv_output_row_drop_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_row_drop_filter_mode',
  'allowed': 'allmatch|anymatch',
  'default': "'anymatch'",
  'kind': 'choice'},
 {'name': 'csv_output_row_filter', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_row_filter_mode',
  'allowed': 'allmatch|anymatch',
  'default': "'allmatch'",
  'kind': 'choice'},
 {'name': 'csv_output_row_limit', 'default': '0', 'kind': 'text'},
 {'name': 'csv_output_sort_headers', 'default': 'Blank', 'kind': 'text'},
 {'name': 'csv_output_subfield_delimiter', 'default': "'.'", 'kind': 'text'},
 {'name': 'csv_output_timestamp_column', 'default': "''", 'kind': 'text'},
 {'name': 'csv_output_users_audit', 'default': 'False', 'kind': 'bool'},
 {'name': 'customer_id', 'default': 'my_customer', 'env': 'CUSTOMER_ID', 'kind': 'text'},
 {'name': 'debug_level', 'default': '0', 'signal': 'OldGamPath/debug.gam', 'kind': 'bool'},
 {'name': 'debug_redaction', 'default': 'True', 'kind': 'bool'},
 {'name': 'developer_preview_apis', 'default': 'Blank', 'kind': 'text'},
 {'name': 'developer_preview_api_key', 'default': 'Blank', 'kind': 'text'},
 {'name': 'device_max_results', 'default': '200', 'range': '1 - 200', 'kind': 'int'},
 {'name': 'domain', 'default': 'Blank', 'env': 'GA_DOMAIN', 'kind': 'text'},
 {'name': 'drive_dir', 'default': '~/Downloads', 'env': 'GAMDRIVEDIR', 'kind': 'text'},
 {'name': 'drive_max_results', 'default': '1000', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'email_batch_size', 'default': '50', 'range': '1 - 100', 'kind': 'int'},
 {'name': 'enable_dasa', 'signal': 'OldGamPath/enabledasa.txt', 'kind': 'bool'},
 {'name': 'event_max_results', 'default': '250', 'range': '1 - 2500', 'kind': 'int'},
 {'name': 'extra_args', 'default': 'Blank', 'kind': 'text'},
 {'name': 'gcp_org_id', 'default': 'Blank', 'kind': 'text'},
 {'name': 'gmail_cse_incert_dir', 'default': 'Blank', 'kind': 'text'},
 {'name': 'gmail_cse_inkey_dir', 'default': 'Blank', 'kind': 'text'},
 {'name': 'input_dir', 'default': '.', 'kind': 'text'},
 {'name': 'inter_batch_wait', 'default': '0', 'range': '0 - 60', 'kind': 'int'},
 {'name': 'license_max_results', 'default': '100', 'range': '10 - 1000', 'kind': 'int'},
 {'name': 'license_skus', 'default': 'Blank', 'kind': 'text'},
 {'name': 'member_max_results', 'default': '200', 'range': '1 - 200', 'kind': 'int'},
 {'name': 'member_max_results_ci_basic', 'default': '1000', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'member_max_results_ci_full', 'default': '500', 'range': '1 - 500', 'kind': 'int'},
 {'name': 'message_batch_size', 'default': '50', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'message_max_results', 'default': '500', 'range': '1 - 10000', 'kind': 'int'},
 {'name': 'mobile_max_results', 'default': '100', 'range': '1 - 100', 'kind': 'int'},
 {'name': 'multiprocess_pool_limit', 'default': '0', 'kind': 'text'},
 {'name': 'never_time', 'default': 'Never', 'kind': 'text'},
 {'name': 'no_browser', 'signal': 'OldGamPath/nobrowser.txt', 'kind': 'bool'},
 {'name': 'no_cache', 'signal': 'OldGamPath/nocache.txt', 'kind': 'bool'},
 {'name': 'no_short_urls', 'default': 'True', 'kind': 'bool'},
 {'name': 'no_verify_ssl', 'default': 'False', 'kind': 'bool'},
 {'name': 'num_tbatch_threads', 'default': '2', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'num_threads', 'default': '5', 'range': '1 - 1000', 'env': 'GAM_THREADS', 'kind': 'int'},
 {'name': 'oauth2_txt',
  'default': '(the GAM config folder)/oauth2.txt',
  'env': 'OAUTHFILE',
  'kind': 'text'},
 {'name': 'oauth2_txt_lock_mode', 'allowed': '644, 664, 666', 'default': '644', 'kind': 'choice'},
 {'name': 'oauth2service_json',
  'default': '(the GAM config folder)/oauth2service.json',
  'env': 'OAUTHSERVICEFILE',
  'kind': 'text'},
 {'name': 'output_dateformat', 'default': "'' which selects the format YYYY-MM-DD", 'kind': 'text'},
 {'name': 'output_timeformat',
  'default': "'' which selects the format YYYY-MM-DDTHH:MM:SS[Z|(+|-)HH:MM)",
  'kind': 'text'},
 {'name': 'people_max_results', 'default': '100', 'range': '1 - 1000', 'kind': 'int'},
 {'name': 'print_agu_domains', 'default': 'Blank', 'kind': 'text'},
 {'name': 'print_cros_ous', 'default': 'Blank', 'kind': 'text'},
 {'name': 'print_cros_ous_and_children', 'default': 'Blank', 'kind': 'text'},
 {'name': 'process_wait_limit', 'default': '0: no limit', 'range': '0 - Unlimited', 'kind': 'int'},
 {'name': 'quick_cros_move', 'default': 'False', 'kind': 'bool'},
 {'name': 'quick_info_user', 'default': 'False', 'kind': 'bool'},
 {'name': 'reseller_id', 'default': 'Blank', 'kind': 'text'},
 {'name': 'retry_api_service_not_available', 'default': 'False', 'kind': 'bool'},
 {'name': 'section', 'default': 'DEFAULT', 'kind': 'text'},
 {'name': 'show_api_calls_retry_data', 'default': 'False', 'kind': 'bool'},
 {'name': 'show_commands', 'default': 'False', 'kind': 'bool'},
 {'name': 'show_convert_cr_nl', 'default': 'False', 'kind': 'bool'},
 {'name': 'show_counts_min', 'default': '1', 'range': '0 - 100', 'kind': 'int'},
 {'name': 'show_gettings', 'default': 'True', 'kind': 'bool'},
 {'name': 'show_gettings_got_nl', 'default': 'False', 'kind': 'bool'},
 {'name': 'show_multiprocess_info', 'default': 'False', 'kind': 'bool'},
 {'name': 'smtp_fqdn', 'default': "''", 'kind': 'text'},
 {'name': 'smtp_host', 'default': "''", 'kind': 'text'},
 {'name': 'smtp_password', 'default': "''", 'kind': 'text', 'secret': True},
 {'name': 'smtp_username', 'default': "''", 'kind': 'text'},
 {'name': 'timezone',
  'default': 'utc',
  'range': 'utc|z|local|(+|-hh:mm)|<ValidTimezoneName>',
  'kind': 'text'},
 {'name': 'tls_max_version',
  'allowed': "'', tlsv1_2, tlsv1.2, tlsv1_3, tlsv1.3",
  'default': "''",
  'kind': 'choice'},
 {'name': 'tls_min_version',
  'allowed': "'', tlsv1_2, tlsv1.2, tlsv1_3, tlsv1.3",
  'default': "''",
  'kind': 'choice'},
 {'name': 'todrive_clearfilter', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_clientaccess', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_conversion', 'default': 'True', 'kind': 'bool'},
 {'name': 'todrive_localcopy', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_locale', 'default': "''", 'kind': 'text'},
 {'name': 'todrive_nobrowser', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_noemail', 'default': 'True', 'kind': 'bool'},
 {'name': 'todrive_no_escape_char', 'default': 'True', 'kind': 'bool'},
 {'name': 'todrive_parent', 'default': 'root', 'kind': 'text'},
 {'name': 'todrive_sheet_timestamp', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_sheet_timeformat',
  'default': "'' which selects an ISO format timestamp",
  'kind': 'text'},
 {'name': 'todrive_timestamp', 'default': 'False', 'kind': 'bool'},
 {'name': 'todrive_timeformat',
  'default': "'' which selects an ISO format timestamp",
  'kind': 'text'},
 {'name': 'todrive_timezone', 'default': "''", 'kind': 'text'},
 {'name': 'todrive_upload_nodata', 'default': 'True', 'kind': 'bool'},
 {'name': 'todrive_user',
  'default': "'' which becomes admin user in admin_email or address from oauth2.txt",
  'kind': 'text'},
 {'name': 'truncate_client_id', 'default': 'False', 'kind': 'bool'},
 {'name': 'update_cros_ou_with_id', 'default': 'False', 'kind': 'bool'},
 {'name': 'use_chat_admin_access', 'default': 'False', 'kind': 'bool'},
 {'name': 'use_course_owner_access', 'default': 'False', 'kind': 'bool'},
 {'name': 'use_projectid_as_name', 'default': 'False', 'kind': 'bool'},
 {'name': 'user_max_results', 'default': '500', 'range': '1 - 500', 'kind': 'int'},
 {'name': 'user_service_account_access_only', 'default': 'False', 'kind': 'bool'}]
