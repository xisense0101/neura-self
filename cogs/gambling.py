# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.


"""
Author: Routo
NeuraSelf-UwU - https://github.com/routo-loop/neura-self
"""




import asyncio
import os
import time
import random
import re
import copy
import core.state as state
from discord.ext import commands

class Gambling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = True
        self.task = None
        self.last_outcomes = {}
        self.gambling_stats = {}
        self._processed_gamble_ids = set()
        uid = str(getattr(self.bot, 'user_id', ''))
        if not uid and hasattr(self.bot, '_connection') and self.bot.user:
            uid = str(self.bot.user.id)
        if not state.account_stats and os.path.exists(state.STATS_FILE):
            state.load_account_stats()
        saved_states = state.account_stats.get(uid, {}).get('martingale_states', {})
        self.martingale_states = copy.deepcopy(saved_states) if saved_states else {}

    def _load_martingale_states(self):
        uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
        if not state.account_stats and os.path.exists(state.STATS_FILE):
            state.load_account_stats()
        saved_states = state.account_stats.get(uid, {}).get('martingale_states', {})
        self.martingale_states = copy.deepcopy(saved_states) if saved_states else {}

    def _save_martingale_states(self):
        uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
        if uid:
            if uid not in state.account_stats:
                state.account_stats[uid] = state.get_empty_stats()
            state.account_stats[uid]['martingale_states'] = copy.deepcopy(self.martingale_states)
            state.save_account_stats()

    def _mark_processed(self, msg_id):
        if not hasattr(self, '_processed_gamble_ids'):
            self._processed_gamble_ids = set()
        self._processed_gamble_ids.add(msg_id)
        if len(self._processed_gamble_ids) > 500:
            self._processed_gamble_ids = set(list(self._processed_gamble_ids)[-250:])

    def _get_gambling_cfg(self):
        return self.bot.config.get('gambling', {})

    def _get_cmd_cfg(self, cmd):
        return self.bot.config.get('commands', {}).get(cmd, {})

    def _get_current_cash(self):
        uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
        st = state.account_stats.get(uid, {})
        return st.get('current_cash', None)

    def _check_safeguards(self, cmd=None, bet_amount=None):
        gamble_cfg = self._get_gambling_cfg()
        min_balance = gamble_cfg.get('min_balance', 0)
        max_balance = gamble_cfg.get('max_balance', 999999999)
        current_cash = self._get_current_cash()
        if current_cash is None:
            self.bot.log("GAMBLING", f"Cash unknown. Skipping {cmd or 'gamble'} bet until balance sync.")
            return False

        if bet_amount is None:
            if cmd is not None:
                bet_amount = self._get_current_bet_for_cmd(cmd)
            else:
                active_cmds = [c for c in ['coinflip', 'slots', 'blackjack'] if hasattr(self.bot, 'cmd_states') and c in self.bot.cmd_states]
                bets = [self._get_current_bet_for_cmd(c) for c in active_cmds]
                bet_amount = max(bets) if bets else 0

        if current_cash < min_balance:
            self.bot.log("GAMBLING", f"Stop-loss: {current_cash} < min {min_balance}. Suspending.")
            if cmd:
                self._reset_martingale_streak(cmd)
            return False
        if current_cash > max_balance:
            self.bot.log("GAMBLING", f"Take-profit: {current_cash} > max {max_balance}. Suspending.")
            return False

        if bet_amount and (current_cash < bet_amount or (current_cash - bet_amount) < min_balance):
            self.bot.log("WARN", f"GAMBLING: Insufficient funds for {cmd} (Cash: {current_cash}, Bet: {bet_amount}, Min: {min_balance}). Resetting Martingale.")
            self._reset_martingale_streak(cmd)
            return False

        return True

    def _reset_martingale_streak(self, cmd=None):
        target_cmds = [cmd] if cmd else list(self.martingale_states.keys())
        if not target_cmds:
            target_cmds = ['coinflip', 'slots', 'blackjack']
        max_bet = self._get_gambling_cfg().get('max_bet', 100000)
        for c in target_cmds:
            cmd_cfg = self._get_cmd_cfg(c)
            base_amount = self.martingale_states.get(c, {}).get('base_bet') or cmd_cfg.get('amount', 1)
            base = min(base_amount, max_bet)
            if c in self.martingale_states:
                self.martingale_states[c]['current_bet'] = base
                self.martingale_states[c]['base_bet'] = base
                self.martingale_states[c]['consecutive_losses'] = 0
                self.martingale_states[c]['consecutive_wins'] = 0
            else:
                self.martingale_states[c] = {
                    'current_bet': base,
                    'base_bet': base,
                    'consecutive_losses': 0,
                    'consecutive_wins': 0
                }
            if hasattr(self.bot, 'cmd_states') and c in self.bot.cmd_states:
                if c == 'coinflip':
                    side = cmd_cfg.get('side', 'h')
                    self.bot.cmd_states[c]['content'] = f"cf {side} {base}"
                elif c == 'slots':
                    self.bot.cmd_states[c]['content'] = f"slots {base}"
                elif c == 'blackjack':
                    self.bot.cmd_states[c]['content'] = f"bj {base}"
        self._save_martingale_states()

    def _parse_blackjack_outcome(self, embed):
        footer = embed.footer.text if embed.footer else ""
        desc = embed.description or ""
        combined = f"{footer} {desc}".lower()
        if "you won" in combined or re.search(r'\b(won|win)\b', combined):
            return "win"
        if "you lost" in combined or re.search(r'\b(lost|lose)\b', combined):
            return "loss"
        if "you tied" in combined or "you both bust" in combined or re.search(r'\b(tied|tie|push)\b', combined):
            return "tie"
        return None

    def _get_bet_amount(self, cmd, base_amount):
        gamble_cfg = self._get_gambling_cfg()
        strategy = gamble_cfg.get('bet_strategy', 'flat')
        max_bet = gamble_cfg.get('max_bet', 100000)

        if strategy == 'martingale':
            if cmd not in self.martingale_states:
                self.martingale_states[cmd] = {
                    'current_bet': base_amount,
                    'base_bet': base_amount,
                    'consecutive_losses': 0,
                    'consecutive_wins': 0
                }
                self._save_martingale_states()
            bet = self.martingale_states[cmd]['current_bet']
            return min(bet, max_bet)
        else:
            return min(base_amount, max_bet)

    def _update_martingale(self, cmd, outcome):
        cmd_cfg = self._get_cmd_cfg(cmd)
        base = cmd_cfg.get('amount', 1)
        if cmd not in self.martingale_states:
            self.martingale_states[cmd] = {
                'current_bet': base,
                'base_bet': base,
                'consecutive_losses': 0,
                'consecutive_wins': 0
            }
        m_state = self.martingale_states[cmd]
        max_bet = self._get_gambling_cfg().get('max_bet', 100000)
        if outcome == 'win':
            m_state['current_bet'] = base
            m_state['consecutive_losses'] = 0
            m_state['consecutive_wins'] += 1
            self.bot.log("GAMBLING", f"Martingale: Won! Reset to {base}")
        elif outcome == 'loss':
            m_state['consecutive_losses'] += 1
            m_state['consecutive_wins'] = 0
            m_state['current_bet'] = min(m_state['current_bet'] * 2, max_bet)
            self.bot.log("GAMBLING", f"Martingale: Lost! Next: {m_state['current_bet']}")
        elif outcome == 'tie':
            self.bot.log("GAMBLING", f"Martingale: Push/Break-even! Holding bet at {m_state['current_bet']}")
        self._save_martingale_states()

    def _record_outcome(self, cmd, outcome, bet_amount, net_profit):
        uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
        if uid not in self.gambling_stats:
            self.gambling_stats[uid] = {
                'total_wins': 0, 'total_losses': 0, 'total_ties': 0, 'total_wagered': 0,
                'net_profit': 0, 'current_streak': 0, 'best_streak': 0,
                'worst_streak': 0, 'biggest_win': 0, 'last_outcome': None
            }
        gs = self.gambling_stats[uid]
        gs['total_wagered'] += bet_amount
        gs['last_outcome'] = outcome
        gs['net_profit'] += net_profit

        if outcome == 'win':
            gs['total_wins'] += 1
            gs['current_streak'] = max(1, gs['current_streak'] + 1) if gs['current_streak'] >= 0 else 1
            gs['best_streak'] = max(gs['best_streak'], gs['current_streak'])
            gs['biggest_win'] = max(gs.get('biggest_win', 0), net_profit)
        elif outcome == 'loss':
            gs['total_losses'] += 1
            gs['current_streak'] = min(-1, gs['current_streak'] - 1) if gs['current_streak'] <= 0 else -1
            gs['worst_streak'] = min(gs.get('worst_streak', 0), gs['current_streak'])
        elif outcome == 'tie':
            gs['total_ties'] = gs.get('total_ties', 0) + 1

        st = state.account_stats.get(uid, {})
        if st:
            st['gambling_stats'] = gs
            if 'current_cash' in st and st['current_cash'] is not None:
                st['current_cash'] = max(0, st['current_cash'] + net_profit)
                st['last_cash_update'] = time.time()
            st['martingale_states'] = copy.deepcopy(self.martingale_states)
            state.save_account_stats()

    def _get_current_bet_for_cmd(self, cmd):
        cmd_cfg = self._get_cmd_cfg(cmd)
        base_amount = cmd_cfg.get('amount', 1)
        return self._get_bet_amount(cmd, base_amount)

    def trigger_coinflip(self):
        if not self._check_safeguards('coinflip'):
            return
        cfg = self._get_cmd_cfg('coinflip')
        amount = self._get_current_bet_for_cmd('coinflip')
        side = cfg.get('side', 'h')
        self.bot.cmd_states['coinflip']['content'] = f"cf {side} {amount}"
        self.bot.cmd_states['coinflip']['delay'] = random.uniform(30, 60)
        self.bot.log("GAMBLING", f"Coinflip: Betting {amount} on {side}")

    def trigger_slots(self):
        if not self._check_safeguards('slots'):
            return
        cfg = self._get_cmd_cfg('slots')
        amount = self._get_current_bet_for_cmd('slots')
        self.bot.cmd_states['slots']['content'] = f"slots {amount}"
        self.bot.cmd_states['slots']['delay'] = random.uniform(25, 50)
        self.bot.log("GAMBLING", f"Slots: Betting {amount}")

    def trigger_blackjack(self):
        if not self._check_safeguards('blackjack'):
            return
        cfg = self._get_cmd_cfg('blackjack')
        amount = self._get_current_bet_for_cmd('blackjack')
        self.bot.cmd_states['blackjack']['content'] = f"bj {amount}"
        self.bot.cmd_states['blackjack']['delay'] = random.uniform(40, 70)
        self.bot.log("GAMBLING", f"Blackjack: Betting {amount}")

    async def register_actions(self):
        cfg_cf = self._get_cmd_cfg('coinflip')
        if cfg_cf.get('enabled', False):
            self.bot.log("SYS", "Gambling (Coinflip) Module configured.")
            await self.bot.neura_register_command("coinflip", "cf", priority=self.bot.get_cmd_priority("coinflip", 3), delay=random.uniform(30, 60), initial_offset=15)
            self.trigger_coinflip()
        cfg_slots = self._get_cmd_cfg('slots')
        if cfg_slots.get('enabled', False):
            self.bot.log("SYS", "Gambling (Slots) Module configured.")
            await self.bot.neura_register_command("slots", "slots", priority=self.bot.get_cmd_priority("slots", 3), delay=random.uniform(25, 50), initial_offset=20)
            self.trigger_slots()
        cfg_bj = self._get_cmd_cfg('blackjack')
        if cfg_bj.get('enabled', False):
            self.bot.log("SYS", "Gambling (Blackjack) Module configured.")
            await self.bot.neura_register_command("blackjack", "bj", priority=self.bot.get_cmd_priority("blackjack", 3), delay=random.uniform(40, 70), initial_offset=25)
            self.trigger_blackjack()

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._process_response(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._process_response(after)

    async def _process_response(self, message):
        core_config = self.bot.config.get('core', {})
        monitor_id = str(core_config.get('monitor_bot_id', '408785106942164992'))
        if str(message.author.id) != monitor_id:
            return
        if self.bot.owo_user is None:
            self.bot.owo_user = message.author
        all_channels = [str(c) for c in self.bot.channels]
        if str(message.channel.id) not in all_channels:
            return
        full_content = self.bot.get_full_content(message)
        is_for_me = self.bot.is_message_for_me(message)
        if not is_for_me:
            return
        content_lower = full_content.lower()

        # Deduplicate message events
        if message.id in self._processed_gamble_ids:
            return

        if "___slots___" in content_lower or "slot" in content_lower:
            # Check if animation is finished (final result line present)
            if "and won" not in content_lower:
                return  # Still spinning animation, wait for edit!

            self._mark_processed(message.id)

            # Extract bet amount from message, e.g. "bet <:cowoncy:416043450337853441> 1"
            bet_match = re.search(r'bet\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower)
            bet_amount = int(bet_match.group(1).replace(',', '')) if bet_match else self._get_current_bet_for_cmd('slots')

            if "nothing" in content_lower:
                # Total loss (0x payout)
                outcome = 'loss'
                net = -bet_amount
            else:
                won_match = re.search(r'and won\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower)
                payout = int(won_match.group(1).replace(',', '')) if won_match else 0
                net = payout - bet_amount
                if net > 0:
                    outcome = 'win'
                elif net == 0:
                    outcome = 'tie'
                else:
                    outcome = 'loss'

            self._handle_gamble_outcome('slots', outcome, bet_amount, net, content_lower)

        elif ("chose" in content_lower and ("heads" in content_lower or "tails" in content_lower)) or "coin spins" in content_lower:
            # Check if coinflip animation is finished
            if "and you won" not in content_lower and "and you lost" not in content_lower and "lands on" not in content_lower and "you lost" not in content_lower and "you won" not in content_lower:
                return  # Still spinning!

            self._mark_processed(message.id)

            bet_match = re.search(r'spent\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower)
            bet_amount = int(bet_match.group(1).replace(',', '')) if bet_match else self._get_current_bet_for_cmd('coinflip')

            if "and you won" in content_lower or "you won" in content_lower:
                won_match = re.search(r'(?:and you won|you won)\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower)
                payout = int(won_match.group(1).replace(',', '')) if won_match else (bet_amount * 2)
                net = payout - bet_amount
                outcome = 'win'
            else:
                outcome = 'loss'
                net = -bet_amount

            self._handle_gamble_outcome('coinflip', outcome, bet_amount, net, content_lower)

        elif "blackjack" in content_lower or "bj" in content_lower:
            outcome = None
            if message.embeds:
                outcome = self._parse_blackjack_outcome(message.embeds[0])

            if outcome in ("win", "loss", "tie"):
                self._mark_processed(message.id)
                embed = message.embeds[0] if message.embeds else None
                author_obj = getattr(embed, 'author', None) if embed else None
                author_name = getattr(author_obj, 'name', '') if author_obj else ""
                footer_obj = getattr(embed, 'footer', None) if embed else None
                footer = getattr(footer_obj, 'text', '') if footer_obj else ""
                desc = getattr(embed, 'description', '') or ""

                # Extract actual bet from author name (e.g. "you bet 2,000 to play blackjack"), description, fields, or message content
                bet_match = re.search(r'bet\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', author_name, re.IGNORECASE)
                if not bet_match and desc:
                    bet_match = re.search(r'bet\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', desc, re.IGNORECASE)
                if not bet_match and embed:
                    for fld in embed.fields:
                        fld_text = f"{fld.name or ''} {fld.value or ''}"
                        bet_match = re.search(r'bet\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', fld_text, re.IGNORECASE)
                        if bet_match:
                            break
                if not bet_match:
                    bet_match = re.search(r'bet\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower, re.IGNORECASE)
                if not bet_match:
                    bet_match = re.search(r'spent\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', content_lower, re.IGNORECASE)

                bet_amount = int(bet_match.group(1).replace(',', '')) if bet_match else self._get_current_bet_for_cmd('blackjack')

                combined = f"{footer} {desc} {content_lower}".lower()

                if outcome == "win":
                    # Check for natural 21 (Blackjack) which pays 3:2 (1.5x profit)
                    is_natural = False
                    if embed:
                        for fld in embed.fields:
                            fname = (fld.name or "").lower()
                            fval = (fld.value or "").lower()
                            if "dealer" not in fname and ("blackjack" in fname or "blackjack" in fval):
                                is_natural = True
                                break
                    if "blackjack!" in combined or "natural" in combined or "3:2" in combined:
                        is_natural = True

                    won_match = re.search(r'(?:and won|you won|won)\s+(?:<a?:\w+:\d+>|:\w+:)?\s*([,\d]+)', combined)
                    if won_match:
                        payout = int(won_match.group(1).replace(',', ''))
                        if payout == int(bet_amount * 1.5):
                            net = payout
                        elif payout == int(bet_amount * 2.5):
                            net = payout - bet_amount
                        elif payout == bet_amount * 2:
                            net = payout - bet_amount
                        elif payout == bet_amount:
                            net = payout
                        elif is_natural:
                            net = int(bet_amount * 1.5)
                        else:
                            net = payout
                    elif is_natural:
                        net = int(bet_amount * 1.5)
                    else:
                        net = bet_amount
                elif outcome == "loss":
                    net = -bet_amount
                else:
                    net = 0
                self._handle_gamble_outcome('blackjack', outcome, bet_amount, net, combined)
            elif outcome is None:
                # In-progress Blackjack game, wait for final embed
                pass

    def _is_recent_gamble(self, cmd):
        if cmd not in self.bot.cmd_states:
            return False
        elapsed = time.time() - self.bot.cmd_states[cmd].get('last_ran', 0)
        return elapsed < 30

    def _handle_gamble_outcome(self, cmd, outcome, bet_amount, net_profit, content):
        self._update_martingale(cmd, outcome)
        self._record_outcome(cmd, outcome, bet_amount, net_profit)

        cmd_cfg = self._get_cmd_cfg(cmd)
        if cmd == 'coinflip':
            side = cmd_cfg.get('side', 'h')
            next_bet = self._get_current_bet_for_cmd('coinflip')
            if hasattr(self.bot, 'cmd_states') and 'coinflip' in self.bot.cmd_states:
                self.bot.cmd_states['coinflip']['content'] = f"cf {side} {next_bet}"
        elif cmd == 'slots':
            next_bet = self._get_current_bet_for_cmd('slots')
            if hasattr(self.bot, 'cmd_states') and 'slots' in self.bot.cmd_states:
                self.bot.cmd_states['slots']['content'] = f"slots {next_bet}"
        elif cmd == 'blackjack':
            next_bet = self._get_current_bet_for_cmd('blackjack')
            if hasattr(self.bot, 'cmd_states') and 'blackjack' in self.bot.cmd_states:
                self.bot.cmd_states['blackjack']['content'] = f"bj {next_bet}"

        self._sync_cash_from_response(content)
        outcome_str = outcome.upper()
        uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
        gs = self.gambling_stats.get(uid, {})
        self.bot.log("GAMBLING", f"{cmd.upper()}: {outcome_str} (Bet: {bet_amount}, Net: {net_profit:+}, Overall Net: {gs.get('net_profit', 0):,})")

    def _sync_cash_from_response(self, content):
        cash_match = re.search(r'(?:now have|balance)[^\d]*([,\d]+)', content, re.IGNORECASE)
        if cash_match:
            try:
                cash_str = cash_match.group(1).replace(',', '')
                cash_val = int(cash_str)
                uid = str(self.bot.user.id) if (hasattr(self.bot, '_connection') and self.bot.user) else str(getattr(self.bot, 'user_id', ''))
                st = state.account_stats.get(uid, {})
                if st:
                    st['current_cash'] = cash_val
                    st['last_cash_update'] = time.time()
                    state.save_account_stats()
            except (ValueError, IndexError):
                pass

async def setup(bot):
    cog = Gambling(bot)
    await bot.add_cog(cog)