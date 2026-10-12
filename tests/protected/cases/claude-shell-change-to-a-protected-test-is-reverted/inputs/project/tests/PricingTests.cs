public class PricingTests
{
    [Fact]
    public void Discount_is_ten_percent() => Assert.Equal(100m, Pricing.Price(100m));
}
