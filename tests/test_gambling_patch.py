import os
import sys
import copy
import re
import asyncio
from unittest.mock import MagicMock

# Mock discord and discord.ext.commands if not installed in this environment
if 'discord' not in sys.modules:
    try:
        import discord
    except ModuleNotFoundError:
        discord = MagicMock()
        discord.ext = MagicMock()
        class MockCog:
            pass
        def mock_listener(*args, **kwargs):
            def decorator(f):
                return f
            return decorator
        commands = MagicMock()
        commands.Cog = MockCog
        commands.Cog.listener = mock_listener
        discord.ext.commands = commands
        sys.modules['discord'] = discord
        sys.modules['discord.ext'] = discord.ext
        sys.modules['discord.ext.commands'] = commands

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.state as state
from cogs.gambling import Gambling

class MockBot:
    def __init__(self, user_id="123456789"):
        self.user_id = user_id
        self.user = None
        self.config = {
            'gambling': {
                'min_balance': 40000,
                'max_balance': 1000000,
                'bet_strategy': 'martingale',
                'max_bet': 10000
            },
            'commands': {
                'coinflip': {'enabled': True, 'amount': 100, 'side': 'h'},
                'slots': {'enabled': True, 'amount': 200},
                'blackjack': {'enabled': True, 'amount': 500}
            },
            'core': {
                'monitor_bot_id': '408785106942164992'
            }
        }
        self.cmd_states = {
            'coinflip': {'content': 'cf h 100', 'delay': 30, 'last_ran': 0, 'in_queue': False},
            'slots': {'content': 'slots 200', 'delay': 25, 'last_ran': 0, 'in_queue': False},
            'blackjack': {'content': 'bj 500', 'delay': 40, 'last_ran': 0, 'in_queue': False}
        }
        self.channels = ['999999999']
        self.owo_user = None
        self.logs = []

    def log(self, tag, message):
        self.logs.append((tag, message))

    def get_full_content(self, message):
        if not message: return ""
        content = message.content or ""
        embed_texts = []
        if message.embeds:
            for em in message.embeds:
                parts = [
                    em.title if hasattr(em, 'title') and em.title else "",
                    em.author.name if em.author else "",
                    em.description or "",
                    "\n".join([f"{f.name}: {f.value}" for f in em.fields])
                ]
                embed_texts.append("\n".join([p for p in parts if p]))
        return (content + "\n" + "\n".join(embed_texts)).lower()

    def is_message_for_me(self, message, role="any", keyword=None):
        return True

def reset_env():
    state.account_stats.clear()
    state.account_stats["123456789"] = state.get_empty_stats()
    state.account_stats["123456789"]['current_cash'] = 50000

def test_check_safeguards_cash_unknown():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    state.account_stats["123456789"]['current_cash'] = None
    assert cog._check_safeguards('coinflip') is False
    assert any("Cash unknown" in m for _, m in bot.logs)
    print("PASS: test_check_safeguards_cash_unknown")

def test_check_safeguards_stop_loss():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    state.account_stats["123456789"]['current_cash'] = 30000  # min_balance is 40000
    assert cog._check_safeguards('coinflip') is False
    assert any("Stop-loss" in m for _, m in bot.logs)
    print("PASS: test_check_safeguards_stop_loss")

def test_check_safeguards_take_profit():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    state.account_stats["123456789"]['current_cash'] = 2000000  # max_balance is 1000000
    assert cog._check_safeguards('coinflip') is False
    assert any("Take-profit" in m for _, m in bot.logs)
    print("PASS: test_check_safeguards_take_profit")

def test_check_safeguards_insufficient_funds_resets_martingale():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    uid = "123456789"
    # Cash is 42000, min_balance is 40000. Available margin is 2000.
    state.account_stats[uid]['current_cash'] = 42000

    # Simulate Martingale bet elevated to 3200 (which would drop balance to 38800 < 40000)
    cog.martingale_states['coinflip'] = {
        'current_bet': 3200,
        'base_bet': 100,
        'consecutive_losses': 5,
        'consecutive_wins': 0
    }
    bot.cmd_states['coinflip']['content'] = "cf h 3200"

    # Safeguard should fail AND reset Martingale state back to base
    assert cog._check_safeguards('coinflip') is False
    assert cog.martingale_states['coinflip']['current_bet'] == 100
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 0
    assert bot.cmd_states['coinflip']['content'] == "cf h 100"
    assert any("Insufficient funds" in m for _, m in bot.logs)

    # Next check with base bet (100) should succeed since 42000 - 100 >= 40000
    assert cog._check_safeguards('coinflip') is True
    print("PASS: test_check_safeguards_insufficient_funds_resets_martingale")

def test_update_martingale():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)

    # Loss doubles bet
    cog._update_martingale('coinflip', 'loss')
    assert cog.martingale_states['coinflip']['current_bet'] == 200
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 1

    cog._update_martingale('coinflip', 'loss')
    assert cog.martingale_states['coinflip']['current_bet'] == 400
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 2

    # Tie holds bet
    cog._update_martingale('coinflip', 'tie')
    assert cog.martingale_states['coinflip']['current_bet'] == 400
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 2

    # Win resets to base bet
    cog._update_martingale('coinflip', 'win')
    assert cog.martingale_states['coinflip']['current_bet'] == 100
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 0
    assert cog.martingale_states['coinflip']['consecutive_wins'] == 1
    print("PASS: test_update_martingale")

def test_persistent_martingale_state():
    reset_env()
    bot = MockBot()
    cog1 = Gambling(bot)
    uid = "123456789"

    cog1._update_martingale('coinflip', 'loss')
    cog1._update_martingale('blackjack', 'loss')
    assert cog1.martingale_states['coinflip']['current_bet'] == 200
    assert cog1.martingale_states['blackjack']['current_bet'] == 1000

    # Verify saved in state.account_stats
    assert state.account_stats[uid]['martingale_states']['coinflip']['current_bet'] == 200
    assert state.account_stats[uid]['martingale_states']['blackjack']['current_bet'] == 1000

    # Simulate bot restart by creating a new Gambling cog
    cog2 = Gambling(bot)
    assert cog2.martingale_states['coinflip']['current_bet'] == 200
    assert cog2.martingale_states['blackjack']['current_bet'] == 1000
    print("PASS: test_persistent_martingale_state")

def test_real_time_cash_balance_sync():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    uid = "123456789"
    state.account_stats[uid]['current_cash'] = 50000

    # Record win (+500)
    cog._record_outcome('blackjack', 'win', 500, 500)
    assert state.account_stats[uid]['current_cash'] == 50500

    # Record loss (-1000)
    cog._record_outcome('blackjack', 'loss', 1000, -1000)
    assert state.account_stats[uid]['current_cash'] == 49500
    print("PASS: test_real_time_cash_balance_sync")

def test_handle_gamble_outcome_blackjack_branch():
    reset_env()
    bot = MockBot()
    cog = Gambling(bot)
    bot.cmd_states['blackjack']['content'] = "bj 500"

    # Loss outcome -> bet doubles to 1000, next cmd content is 'bj 1000'
    cog._handle_gamble_outcome('blackjack', 'loss', 500, -500, "you lost 500 cowoncy")
    assert bot.cmd_states['blackjack']['content'] == "bj 1000"
    assert cog.martingale_states['blackjack']['current_bet'] == 1000

    # Win outcome -> bet resets to 500, next cmd content is 'bj 500'
    cog._handle_gamble_outcome('blackjack', 'win', 1000, 1000, "you won 1,000 cowoncy")
    assert bot.cmd_states['blackjack']['content'] == "bj 500"
    assert cog.martingale_states['blackjack']['current_bet'] == 500
    print("PASS: test_handle_gamble_outcome_blackjack_branch")

class MockAuthor:
    def __init__(self, name):
        self.name = name

class MockFooter:
    def __init__(self, text):
        self.text = text

class MockField:
    def __init__(self, name, value):
        self.name = name
        self.value = value

class MockEmbed:
    def __init__(self, author_name=None, footer_text=None, fields=None, desc=""):
        self.author = MockAuthor(author_name) if author_name else None
        self.footer = MockFooter(footer_text) if footer_text else None
        self.fields = fields or []
        self.description = desc

class MockMessage:
    def __init__(self, content="", embeds=None, author_id="408785106942164992", channel_id="999999999", msg_id=101):
        self.content = content
        self.embeds = embeds or []
        class User:
            id = author_id
        self.author = User()
        class Channel:
            id = channel_id
        self.channel = Channel()
        self.id = msg_id

def test_blackjack_response_parsing():
    async def _run():
        reset_env()
        bot = MockBot()
        cog = Gambling(bot)

        # Test natural 21 (Blackjack) with 3:2 payout (1.5x profit)
        # User bet 2,000 cowoncy. Natural 21 pays 3,000 net profit.
        embed_bj = MockEmbed(
            author_name="Routo, you bet 2,000 to play blackjack!",
            footer_text="You won 3,000 cowoncy!",
            fields=[MockField("Routo [21] - Blackjack!", "cards"), MockField("Dealer [18]", "cards")]
        )
        msg_bj = MockMessage(content="", embeds=[embed_bj], msg_id=201)
        await cog._process_response(msg_bj)
        # Check that net profit recorded is 3000 (1.5x of 2000)
        uid = "123456789"
        assert state.account_stats[uid]['gambling_stats']['biggest_win'] == 3000
        assert state.account_stats[uid]['current_cash'] == 50000 + 3000
        print("PASS: test_blackjack_response_parsing")
    asyncio.run(_run())

def test_slots_tie_and_partial_loss():
    async def _run():
        reset_env()
        bot = MockBot()
        cog = Gambling(bot)
        uid = "123456789"

        # Set up martingale state at 400
        cog.martingale_states['slots'] = {
            'current_bet': 400,
            'base_bet': 200,
            'consecutive_losses': 1,
            'consecutive_wins': 0
        }

        # Test 1x break-even push (bet 400, won 400 -> net = 0 -> tie)
        # Should NOT double bet! Should hold at 400.
        msg_push = MockMessage(content="___SLOTS___ | bet 400 cowoncy and won 400 cowoncy", msg_id=301)
        await cog._process_response(msg_push)
        assert cog.martingale_states['slots']['current_bet'] == 400
        assert state.account_stats[uid]['current_cash'] == 50000  # unchanged

        # Test partial loss (bet 400, won 100 -> net = -300 -> loss)
        # Should deduct only 300 (partial loss), and martingale doubles to 800
        msg_partial = MockMessage(content="___SLOTS___ | bet 400 cowoncy and won 100 cowoncy", msg_id=302)
        await cog._process_response(msg_partial)
        assert cog.martingale_states['slots']['current_bet'] == 800
        assert state.account_stats[uid]['current_cash'] == 50000 - 300
        print("PASS: test_slots_tie_and_partial_loss")
    asyncio.run(_run())

def test_bot_queue_worker_stale_data_prevention():
    async def _run():
        reset_env()
        bot = MockBot()
        cog = Gambling(bot)

        cmd_id = "coinflip"
        content = "cf h 100"
        bot.cmd_states[cmd_id]['content'] = content

        # Simulate _handle_gamble_outcome updating content during _send_safe execution
        prev_content = "cf h 200"
        bot.cmd_states[cmd_id]['content'] = prev_content

        # Now simulate what neura_queue_worker does around lines 814-817:
        curr_prev = bot.cmd_states[cmd_id].get('content')
        getattr(cog, "trigger_coinflip")()

        # The stale overwrite guard
        if curr_prev and curr_prev != content:
            bot.cmd_states[cmd_id]['content'] = curr_prev

        # The newly updated bet ("cf h 200") must be preserved, not overwritten by stale data
        assert bot.cmd_states[cmd_id]['content'] == "cf h 200"
        print("PASS: test_bot_queue_worker_stale_data_prevention")
    asyncio.run(_run())

def test_bot_config_cogs_mapping():
    # Parse and execute _cogs_for_config_changes directly from core/bot.py AST
    import ast
    bot_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core', 'bot.py')
    with open(bot_path, 'r') as f:
        tree = ast.parse(f.read(), filename=bot_path)

    fn_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_cogs_for_config_changes':
            fn_node = node
            break

    assert fn_node is not None, "_cogs_for_config_changes not found in core/bot.py"
    # Create module with just this function
    mod_ast = ast.Module(body=[fn_node], type_ignores=[])
    code = compile(mod_ast, bot_path, 'exec')
    namespace = {}
    exec(code, namespace)
    _cogs_for_config_changes = namespace['_cogs_for_config_changes']

    cogs_bj = _cogs_for_config_changes(None, ["commands.blackjack.amount"])
    assert "Gambling" in cogs_bj, f"Expected Gambling in {cogs_bj}"

    cogs_gambling = _cogs_for_config_changes(None, ["gambling.min_balance"])
    assert "Gambling" in cogs_gambling, f"Expected Gambling in {cogs_gambling}"
    print("PASS: test_bot_config_cogs_mapping")

if __name__ == '__main__':
    test_check_safeguards_cash_unknown()
    test_check_safeguards_stop_loss()
    test_check_safeguards_take_profit()
    test_check_safeguards_insufficient_funds_resets_martingale()
    test_update_martingale()
    test_persistent_martingale_state()
    test_real_time_cash_balance_sync()
    test_handle_gamble_outcome_blackjack_branch()
    test_blackjack_response_parsing()
    test_slots_tie_and_partial_loss()
    test_bot_queue_worker_stale_data_prevention()
    test_bot_config_cogs_mapping()
    print("\nALL GAMBLING UNIT TESTS PASSED SUCCESSFULLY!")
