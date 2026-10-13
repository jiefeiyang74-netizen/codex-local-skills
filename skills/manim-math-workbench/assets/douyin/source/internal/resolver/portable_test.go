package resolver
import "testing"
func TestPortableURLBoundary(t *testing.T){
 for _,s:=range []string{"https://127.0.0.1/video/123", "https://v.douyin.com.evil.example/video/123", "https://evil.example/?x=douyin.com/video/123", "https://u:p@v.douyin.com/abc", "file:///video/123", "https://v.douyin.com:443/abc"}{
  if IsDouyinURL(s){t.Fatal("accepted",s)}
 }
 got,e:=Resolve("https://www.douyin.com/video/1234567890123");if e!=nil||got!="https://www.douyin.com/video/1234567890123"{t.Fatal(got,e)}
}
