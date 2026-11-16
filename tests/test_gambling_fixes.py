import os
import json
import time
import pytest
import core.state as state
from cogs.gambling import Gambling


class MockUser:
    def __init__(self, uid=1451414972377862228, name="testuser"):
        self.id = uid
        self.name = name


class MockEmbedFooter:
    def __init__(self, text):
        self.text = text


class MockEmbed:
    def __init__(self, footer_text="", description=""):
        self.footer = MockEmbedFooter(footer_text) if footer_text else None
        self.description = description
        self.fields = []
        self.author = None


_mock_msg_id_counter = 1000000

class MockMessage:
    def __init__(self, content="", embeds=None, author_id=408785106942164992, channel_id=123456):
        global _mock_msg_id_counter
        _mock_msg_id_counter += 1
        self.id = _mock_msg_id_counter
        self.content = content
        self.embeds = embeds or []
        self.author = MockUser(uid=author_id, name="OwO")
        self.channel = MockUser(uid=channel_id, name="channel")


class MockBot:
    def __init__(self, user_id="1451414972377862228"):
        self.user_id = str(user_id)
        self.user = MockUser(uid=int(user_id))
        self.channels = [123456]
        self.owo_user = None
        self.config = {
            'core': {'monitor_bot_id': '408785106942164992'},
            'commands': {
                'coinflip': {'enabled': True, 'amount': 100, 'side': 'h'},
                'slots': {'enabled': True, 'amount': 200},
                'blackjack': {'enabled': True, 'amount': 500}
            },
            'gambling': {
                'min_balance': 10000,
                'max_balance': 1000000,
                'bet_strategy': 'martingale',
                'max_bet': 4000
            }
        }
        self.cmd_states = {
            'coinflip': {'content': 'cf h 100', 'delay': 30, 'last_ran': time.time(), 'in_queue': False},
            'slots': {'content': 'slots 200', 'delay': 30, 'last_ran': time.time(), 'in_queue': False},
            'blackjack': {'content': 'bj 500', 'delay': 30, 'last_ran': time.time(), 'in_queue': False}
        }
        self.logs = []

    def log(self, tag, msg):
        self.logs.append((tag, msg))

    def get_full_content(self, message):
        c = message.content or ""
        for em in message.embeds:
            if em.footer and em.footer.text:
                c += " " + em.footer.text
            if em.description:
                c += " " + em.description
        return c.lower()

    def is_message_for_me(self, message):
        return True


def setup_clean_state(tmp_path, uid="1451414972377862228"):
    stats_file = str(tmp_path / "stats.json")
    state.STATS_FILE = stats_file
    state.account_stats = {
        uid: state.get_empty_stats()
    }
    state.account_stats[uid]['current_cash'] = 50000
    state.account_stats[uid]['username'] = "testuser"
    state.save_account_stats()
    return stats_file


def test_martingale_persistence(tmp_path):
    uid = "1451414972377862228"
    stats_file = setup_clean_state(tmp_path, uid)

    bot1 = MockBot(uid)
    cog1 = Gambling(bot1)

    # Simulate 1 loss on coinflip
    cog1._handle_gamble_outcome('coinflip', 'loss', 100, -100, "you lost 100")

    # Bet should have doubled to 200
    assert cog1.martingale_states['coinflip']['current_bet'] == 200
    assert cog1.martingale_states['coinflip']['consecutive_losses'] == 1
    assert bot1.cmd_states['coinflip']['content'] == "cf h 200"

    # Verify saved on disk in stats.json
    with open(stats_file, 'r') as f:
        saved_data = json.load(f)
    assert 'martingale_states' in saved_data[uid]
    assert saved_data[uid]['martingale_states']['coinflip']['current_bet'] == 200

    # Simulate bot restart (new Cog instance loading from state/disk)
    bot2 = MockBot(uid)
    cog2 = Gambling(bot2)

    assert 'coinflip' in cog2.martingale_states
    assert cog2.martingale_states['coinflip']['current_bet'] == 200
    assert cog2.martingale_states['coinflip']['consecutive_losses'] == 1

    # Win next round -> should reset to base bet (100)
    cog2._handle_gamble_outcome('coinflip', 'win', 200, 200, "and you won 400")
    assert cog2.martingale_states['coinflip']['current_bet'] == 100
    assert cog2.martingale_states['coinflip']['consecutive_losses'] == 0
    assert bot2.cmd_states['coinflip']['content'] == "cf h 100"


def test_blackjack_outcome_and_cmd_state_updates(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    cog = Gambling(bot)

    # Initial state
    assert bot.cmd_states['blackjack']['content'] == "bj 500"

    # 1. Loss on blackjack -> should double to 1000 and update cmd_states
    cog._handle_gamble_outcome('blackjack', 'loss', 500, -500, "you lost")
    assert cog.martingale_states['blackjack']['current_bet'] == 1000
    assert bot.cmd_states['blackjack']['content'] == "bj 1000"

    # 2. Second loss -> doubles to 2000
    cog._handle_gamble_outcome('blackjack', 'loss', 1000, -1000, "you lost")
    assert cog.martingale_states['blackjack']['current_bet'] == 2000
    assert bot.cmd_states['blackjack']['content'] == "bj 2000"

    # 3. Tie / Push -> bet remains at 2000
    cog._handle_gamble_outcome('blackjack', 'tie', 2000, 0, "you tied")
    assert cog.martingale_states['blackjack']['current_bet'] == 2000
    assert bot.cmd_states['blackjack']['content'] == "bj 2000"

    # 4. Natural 3:2 win -> resets to base (500)
    cog._handle_gamble_outcome('blackjack', 'win', 2000, 3000, "you won 5,000 cowoncy! natural blackjack")
    assert cog.martingale_states['blackjack']['current_bet'] == 500
    assert cog.martingale_states['blackjack']['consecutive_losses'] == 0
    assert bot.cmd_states['blackjack']['content'] == "bj 500"


def test_real_time_cash_sync(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    cog = Gambling(bot)

    initial_cash = state.account_stats[uid]['current_cash']
    assert initial_cash == 50000

    # Win 500
    cog._handle_gamble_outcome('coinflip', 'win', 500, 500, "and you won 1000")
    assert state.account_stats[uid]['current_cash'] == 50500

    # Loss 1000
    cog._handle_gamble_outcome('coinflip', 'loss', 1000, -1000, "and you lost 1000")
    assert state.account_stats[uid]['current_cash'] == 49500

    # Explicit cash text in response
    cog._sync_cash_from_response("You now have 62,340 cowoncy!")
    assert state.account_stats[uid]['current_cash'] == 62340


def test_strict_bankroll_safeguards_reset_streak(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    # min_balance is 10000
    cog = Gambling(bot)

    # Set Martingale bet high (say, 3200)
    cog.martingale_states['coinflip'] = {
        'current_bet': 3200,
        'base_bet': 100,
        'consecutive_losses': 5,
        'consecutive_wins': 0
    }
    bot.cmd_states['coinflip']['content'] = "cf h 3200"

    # Case A: Cash is 12000, but bet 3200 would bring balance to 8800 (< min_balance 10000)
    state.account_stats[uid]['current_cash'] = 12000
    can_bet = cog._check_safeguards('coinflip', 3200)

    # Must reject bet AND reset streak to base
    assert can_bet is False
    assert cog.martingale_states['coinflip']['current_bet'] == 100
    assert cog.martingale_states['coinflip']['consecutive_losses'] == 0
    assert bot.cmd_states['coinflip']['content'] == "cf h 100"

    # Case A2: current_cash < bet_amount directly (e.g. min_balance is 0, cash is 250, bet is 500)
    bot.config['gambling']['min_balance'] = 0
    state.account_stats[uid]['current_cash'] = 250
    cog.martingale_states['blackjack'] = {
        'current_bet': 500,
        'base_bet': 100,
        'consecutive_losses': 2,
        'consecutive_wins': 0
    }
    bot.cmd_states['blackjack']['content'] = "bj 500"
    can_bet_unaffordable = cog._check_safeguards('blackjack')
    assert can_bet_unaffordable is False
    assert cog.martingale_states['blackjack']['current_bet'] == 100
    assert bot.cmd_states['blackjack']['content'] == "bj 100"

    # Case B: Cash is below min_balance directly (e.g. 9000 < 10000)
    bot.config['gambling']['min_balance'] = 10000
    state.account_stats[uid]['current_cash'] = 9000
    can_bet_stoploss = cog._check_safeguards('coinflip')
    assert can_bet_stoploss is False

    # Case C: Cash unknown (None)
    state.account_stats[uid]['current_cash'] = None
    can_bet_unknown = cog._check_safeguards('coinflip')
    assert can_bet_unknown is False


def test_max_bet_clamping(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    # max_bet is 4000
    cog = Gambling(bot)

    # Trigger multiple losses
    bet = cog._get_bet_amount('coinflip', 100)
    assert bet == 100

    for _ in range(10):
        cog._handle_gamble_outcome('coinflip', 'loss', bet, -bet, "you lost")
        bet = cog._get_current_bet_for_cmd('coinflip')

    # Bet must be strictly clamped to max_bet (4000)
    assert cog.martingale_states['coinflip']['current_bet'] == 4000
    assert bot.cmd_states['coinflip']['content'] == "cf h 4000"


def test_slots_tie_does_not_double(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    cog = Gambling(bot)

    # Base bet is 200
    assert cog._get_current_bet_for_cmd('slots') == 200

    # Loss doubles to 400
    cog._handle_gamble_outcome('slots', 'loss', 200, -200, "nothing")
    assert cog.martingale_states['slots']['current_bet'] == 400

    # 1x Break-even push (tie) holds bet at 400 without doubling
    cog._handle_gamble_outcome('slots', 'tie', 400, 0, "and won 400")
    assert cog.martingale_states['slots']['current_bet'] == 400
    assert bot.cmd_states['slots']['content'] == "slots 400"


@pytest.mark.asyncio
async def test_blackjack_message_events_all_outcomes(tmp_path):
    uid = "1451414972377862228"
    setup_clean_state(tmp_path, uid)

    bot = MockBot(uid)
    cog = Gambling(bot)

    # 1. Message Event: Loss
    loss_msg = MockMessage(
        content="owo bj 500",
        embeds=[MockEmbed(footer_text="You lost 500 cowoncy", description="Dealer [20], Player [18]")]
    )
    await cog.on_message(loss_msg)
    assert cog.martingale_states['blackjack']['current_bet'] == 1000
    assert bot.cmd_states['blackjack']['content'] == "bj 1000"

    # 2. Message Event: Tie / Push
    tie_msg = MockMessage(
        content="owo bj 1000",
        embeds=[MockEmbed(footer_text="You tied! Bet returned.", description="Dealer [19], Player [19]")]
    )
    await cog.on_message(tie_msg)
    assert cog.martingale_states['blackjack']['current_bet'] == 1000
    assert bot.cmd_states['blackjack']['content'] == "bj 1000"

    # 3. Message Event: Natural 3:2 Blackjack Win
    nat_msg = MockMessage(
        content="owo bj 1000",
        embeds=[MockEmbed(footer_text="You won 1,500 cowoncy", description="Dealer [18], Player [21]* Natural Blackjack!")]
    )
    await cog.on_message(nat_msg)
    assert cog.martingale_states['blackjack']['current_bet'] == 500
    assert bot.cmd_states['blackjack']['content'] == "bj 500"

    # 4. Message Event: Regular Win
    loss_msg2 = MockMessage(
        content="owo bj 500",
        embeds=[MockEmbed(footer_text="You lost 500 cowoncy", description="Dealer [21], Player [17]")]
    )
    await cog.on_message(loss_msg2)
    assert cog.martingale_states['blackjack']['current_bet'] == 1000
    assert bot.cmd_states['blackjack']['content'] == "bj 1000"

    win_msg = MockMessage(
        content="owo bj 1000",
        embeds=[MockEmbed(footer_text="You won 1,000 cowoncy", description="Dealer [17], Player [20]")]
    )
    await cog.on_message(win_msg)
    assert cog.martingale_states['blackjack']['current_bet'] == 500
    assert bot.cmd_states['blackjack']['content'] == "bj 500"
