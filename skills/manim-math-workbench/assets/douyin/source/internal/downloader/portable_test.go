package downloader
import("testing";"net/http";"net/url")
func TestMediaBoundary(t *testing.T){
 for _,s:=range []string{"http://v.douyinvod.com/a", "https://localhost/a", "https://127.0.0.1/a", "https://douyinvod.com.evil.example/a", "file:///a", "https://u:p@v.douyinvod.com/a"}{if safeMediaURL(s){t.Fatal(s)}}
 if !safeMediaURL("https://v3.douyinvod.com/a"){t.Fatal("known CDN rejected")}
 u,_:=url.Parse("https://127.0.0.1/private");if safeRedirect(&http.Request{URL:u},nil)==nil{t.Fatal("redirect accepted")}
}
