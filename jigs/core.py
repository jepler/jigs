# SPDX-FileCopyrightText: 2023 Jeff Epler
#
# SPDX-License-Identifier: GPL-3.0-only

import re

unsafe_chars = re.compile(r"[^a-zA-Z0-9-_]+")
