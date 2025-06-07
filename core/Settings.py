class Settings:
    def __init__(self, to_network, allowance, delay_after_approve, gas_amount, gas_price_limits=None):
        self.to_network = to_network
        self.allowance = allowance
        self.delay_after_approve = delay_after_approve
        self.gas_amount = gas_amount
        self.gas_price_limits = gas_price_limits