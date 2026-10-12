public class TaxTests
{
    [Fact]
    public void Tax_is_twenty_percent() => Assert.Equal(20m, Tax.Of(100m));
}
