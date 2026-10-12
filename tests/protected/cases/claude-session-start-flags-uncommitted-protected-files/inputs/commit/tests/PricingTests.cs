public class PricingTests
{
    [Fact]
    public void Discount_is_ten_percent() => Assert.Equal(90m, Pricing.Price(100m));
}
