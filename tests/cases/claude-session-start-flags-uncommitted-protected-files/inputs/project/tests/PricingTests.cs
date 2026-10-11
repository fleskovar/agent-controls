public class PricingTests
{
    [Fact]
    public void Discount_is_twenty_percent() => Assert.Equal(80m, Pricing.Price(100m));
}
