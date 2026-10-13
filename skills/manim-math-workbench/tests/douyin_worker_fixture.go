// Mock subprocess for long-log/audio-path regression only. Not a transcriber.
package main
import("os";"path/filepath";"fmt";"strings";"time")
func main(){
 audio,_:=filepath.Abs("中文音频.mp3")
 os.WriteFile(audio,[]byte("MOCK retained audio"),0600)
 b:=[]byte("Audio saved: "+audio+"\n")
 // Deliberately split multibyte path characters across writes.
 for _,v:=range b {os.Stderr.Write([]byte{v})}
 fmt.Fprintln(os.Stderr,strings.Repeat("long log line\n",15000))
 for i,a:=range os.Args{if a=="-o"&&i+1<len(os.Args){os.WriteFile(os.Args[i+1],[]byte("mock transcript"),0600)}}
 if os.Getenv("DOUYIN_FIXTURE_HANG")=="1"{time.Sleep(30*time.Second)}
}
