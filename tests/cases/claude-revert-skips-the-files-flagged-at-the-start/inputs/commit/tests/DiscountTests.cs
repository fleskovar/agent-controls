public class DiscountTests
{
    [Fact]
    public void No_discount_below_ten() => Assert.Equal(5m, Pricing.Price(5m));
}
