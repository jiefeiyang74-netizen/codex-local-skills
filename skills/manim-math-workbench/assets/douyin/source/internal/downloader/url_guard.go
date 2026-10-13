package downloader

import("fmt";"net/http";"net/url";"strings")

// Deliberately fail closed if Douyin adopts an unlisted CDN. Do not accept arbitrary hosts.
func safeMediaURL(raw string) bool {
 u,e:=url.Parse(raw);if e!=nil||u.Scheme!="https"||u.User!=nil||u.Port()!="" {return false}
 h:=strings.ToLower(u.Hostname())
 for _,domain:=range []string{"douyin.com","iesdouyin.com","douyinvod.com","bytecdn.cn","bytecdntp.com","ibytedtos.com","pstatp.com","snssdk.com"}{
  if h==domain||strings.HasSuffix(h,"."+domain){return true}
 }
 return false
}
func safeRedirect(req *http.Request,via []*http.Request)error{
 if len(via)>=8||!safeMediaURL(req.URL.String()){return fmt.Errorf("unapproved redirect")};return nil
}
