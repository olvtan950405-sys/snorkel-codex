package main

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	bolt "go.etcd.io/bbolt"
)

type request struct { Method string `json:"method"`; Path string `json:"path"`; Body map[string]any `json:"body"` }
type tokenRow struct { LeaseID string `json:"lease_id"`; Subject string `json:"subject"`; Kid string `json:"kid"`; Iat int64 `json:"iat"`; Exp int64 `json:"exp"` }
type leaseRow struct { ID string `json:"id"`; Subject string `json:"subject"`; Kid string `json:"kid"`; ExpiresAt int64 `json:"expires_at"` }
type moduleIn struct { Module string `json:"module"`; Version string `json:"version"`; Remote string `json:"remote"`; Tag string `json:"tag"` }
type moduleRow struct { Module string `json:"module"`; Version string `json:"version"`; Tag string `json:"tag"`; Commit string `json:"commit"` }
type report struct { Tokens []tokenRow `json:"tokens"`; Leases []leaseRow `json:"leases"`; Modules []moduleRow `json:"modules"` }

func strict(path string, out any) error { b,e:=os.ReadFile(path); if e!=nil{return e}; d:=json.NewDecoder(bytes.NewReader(b)); d.DisallowUnknownFields(); if e=d.Decode(out);e!=nil{return e}; if d.Decode(&struct{}{})!=io.EOF{return errors.New("trailing JSON")}; return nil }
func command(name string,args ...string)(string,error){ c:=exec.Command(name,args...); var o,e bytes.Buffer;c.Stdout=&o;c.Stderr=&e;err:=c.Run();if err!=nil{return "",fmt.Errorf("%s: %w",strings.TrimSpace(e.String()),err)};return o.String(),nil }

func discover(pid int)(string,string,error){
	var netout,files string; var e error
	for i:=0;i<80;i++ { netout,e=command("lsof","-Pan","-p",strconv.Itoa(pid),"-iTCP","-sTCP:LISTEN"); if e==nil && strings.Contains(netout,"LISTEN"){break}; time.Sleep(25*time.Millisecond) }
	if e!=nil{return "","",e}; re:=regexp.MustCompile(`127\.0\.0\.1:(\d+).*LISTEN`); m:=re.FindStringSubmatch(netout);if m==nil{return "","",errors.New("listener not discovered")}
	files,e=command("lsof","-Fn","-p",strconv.Itoa(pid));if e!=nil{return "","",e}; db:="";for _,x:=range strings.Split(files,"\n"){if strings.HasPrefix(x,"n")&&strings.HasSuffix(x,".db"){db=strings.TrimPrefix(x,"n")}}
	if db==""{return "","",errors.New("database not discovered")};return m[1],db,nil
}
func jwks(url,kid string)(ed25519.PublicKey,error){
	r,err:=http.Get(url+"/.well-known/jwks.json");if err!=nil{return nil,err};defer r.Body.Close();if r.StatusCode!=200{return nil,errors.New("jwks status")};var x struct{Keys []struct{Kid,Kty,Crv,Alg,Use,X string}};d:=json.NewDecoder(io.LimitReader(r.Body,1<<20));if d.Decode(&x)!=nil{return nil,errors.New("bad jwks")};var found []byte
	for _,k:=range x.Keys{if k.Kid==kid&&k.Kty=="OKP"&&k.Crv=="Ed25519"&&k.Alg=="EdDSA"&&k.Use=="sig"{p,e:=base64.RawURLEncoding.DecodeString(k.X);if e==nil&&len(p)==ed25519.PublicKeySize{if found!=nil{return nil,errors.New("duplicate kid")};found=p}}};if found==nil{return nil,errors.New("kid absent")};return ed25519.PublicKey(found),nil
}
func verify(raw,base string)(tokenRow,error){
	parts:=strings.Split(raw,".");if len(parts)!=3{return tokenRow{},errors.New("bad jwt")};hb,e:=base64.RawURLEncoding.DecodeString(parts[0]);if e!=nil{return tokenRow{},e};var h struct{Alg,Typ,Kid string};d:=json.NewDecoder(bytes.NewReader(hb));d.DisallowUnknownFields();if d.Decode(&h)!=nil||h.Alg!="EdDSA"||h.Typ!="JWT"||h.Kid==""{return tokenRow{},errors.New("bad header")};pub,e:=jwks(base,h.Kid);if e!=nil{return tokenRow{},e}
	tok,e:=jwt.Parse(raw,func(t *jwt.Token)(any,error){if t.Method!=jwt.SigningMethodEdDSA{return nil,errors.New("algorithm")};return pub,nil},jwt.WithIssuer("locksmith"),jwt.WithAudience("lease-clients"));if e!=nil||!tok.Valid{return tokenRow{},errors.New("signature or claims")};c,ok:=tok.Claims.(jwt.MapClaims);if !ok{return tokenRow{},errors.New("claims")}; sub,sok:=c["sub"].(string);id,iok:=c["lease_id"].(string);iat,ie:=c.GetIssuedAt();exp,ee:=c.GetExpirationTime();if !sok||!iok||sub==""||id==""||ie!=nil||ee!=nil||iat==nil||exp==nil||exp.Unix()<=iat.Unix(){return tokenRow{},errors.New("claim shape")};return tokenRow{id,sub,h.Kid,iat.Unix(),exp.Unix()},nil
}
func modules(path string)([]moduleRow,error){
	var p struct{Modules []moduleIn `json:"modules"`};if e:=strict(path,&p);e!=nil{return nil,e};seen:=map[string]bool{};out:=[]moduleRow{};sem:=regexp.MustCompile(`^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`);hex:=regexp.MustCompile(`^[0-9a-f]{40}$`)
	for _,m:=range p.Modules{key:=m.Module+"\x00"+m.Version;if m.Module==""||m.Remote==""||m.Tag!=m.Version||!sem.MatchString(m.Version)||seen[key]{return nil,errors.New("invalid module policy")};seen[key]=true;ref:="refs/tags/"+m.Tag;o,e:=command("git","ls-remote","--tags","--",m.Remote,ref,ref+"^{}");if e!=nil{return nil,e};direct,peeled:="","";for _,l:=range strings.Split(strings.TrimSpace(o),"\n"){f:=strings.Fields(l);if len(f)!=2{continue};if f[1]==ref{direct=f[0]};if f[1]==ref+"^{}"{peeled=f[0]}};commit:=peeled;if commit==""{commit=direct};if !hex.MatchString(commit){return nil,errors.New("tag resolution")}
		ctx,cancel:=context.WithTimeout(context.Background(),2*time.Minute);c:=exec.CommandContext(ctx,"go","mod","download","-json",m.Module+"@"+m.Version);b,e:=c.Output();cancel();if e!=nil{return nil,e};var g struct{Origin *struct{Hash,Ref string}};if json.Unmarshal(b,&g)!=nil||g.Origin==nil||g.Origin.Hash!=commit||g.Origin.Ref!=ref{return nil,errors.New("module origin mismatch")};out=append(out,moduleRow{m.Module,m.Version,m.Tag,commit}) }
	sort.Slice(out,func(i,j int)bool{if out[i].Module==out[j].Module{return out[i].Version<out[j].Version};return out[i].Module<out[j].Module});return out,nil
}
func main(){
	api:=flag.String("api","","fixture binary");requests:=flag.String("requests","","requests");mods:=flag.String("modules","","modules");master:=flag.String("master-key","","key");dest:=flag.String("report","","report");flag.Parse();if *api==""||*requests==""||*mods==""||*dest==""||len([]byte(*master))!=32{fmt.Fprintln(os.Stderr,"invalid arguments");os.Exit(2)}
	var reqs []request;if strict(*requests,&reqs)!=nil||len(reqs)==0{fmt.Fprintln(os.Stderr,"invalid requests");panic("audit failed")};tmp,e:=os.MkdirTemp("","locksmith-audit-");if e!=nil{panic(e)};defer os.RemoveAll(tmp);expected:=filepath.Join(tmp,"runtime.db");cmd:=exec.Command(*api);cmd.Env=append(os.Environ(),"LOCKSMITH_MASTER_KEY="+*master,"LOCKSMITH_DB="+expected);cmd.Stdout=io.Discard;cmd.Stderr=os.Stderr;if e=cmd.Start();e!=nil{panic(e)};defer func(){if cmd.ProcessState==nil{cmd.Process.Signal(syscall.SIGTERM);cmd.Wait()}}();port,dbPath,e:=discover(cmd.Process.Pid);if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};base:="http://127.0.0.1:"+port;tokens:=[]tokenRow{}
	for _,q:=range reqs{if q.Method!="POST"||!strings.HasPrefix(q.Path,"/")||strings.Contains(q.Path,"..") {fmt.Fprintln(os.Stderr,"invalid request");panic("audit failed")};body,_:=json.Marshal(q.Body);r,e:=http.Post(base+q.Path,"application/json",bytes.NewReader(body));if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};b,_:=io.ReadAll(io.LimitReader(r.Body,1<<20));r.Body.Close();if r.StatusCode<200||r.StatusCode>=300{fmt.Fprintln(os.Stderr,"request failed");panic("audit failed")};if q.Path=="/leases"{var x struct{Token string `json:"token"`};d:=json.NewDecoder(bytes.NewReader(b));d.DisallowUnknownFields();if d.Decode(&x)!=nil||x.Token==""{fmt.Fprintln(os.Stderr,"bad lease response");panic("audit failed")};t,e:=verify(x.Token,base);if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};tokens=append(tokens,t)}}
	cmd.Process.Signal(syscall.SIGTERM);cmd.Wait();sort.Slice(tokens,func(i,j int)bool{return tokens[i].LeaseID<tokens[j].LeaseID});leases:=[]leaseRow{};block,_:=aes.NewCipher([]byte(*master));g,_:=cipher.NewGCM(block);db,e:=bolt.Open(dbPath,0600,&bolt.Options{ReadOnly:true});if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};e=db.View(func(tx *bolt.Tx)error{b:=tx.Bucket([]byte("leases"));if b==nil{return errors.New("bucket missing")};return b.ForEach(func(k,v []byte)error{if len(v)<g.NonceSize(){return errors.New("short record")};plain,e:=g.Open(nil,v[:g.NonceSize()],v[g.NonceSize():],k);if e!=nil{return e};var x leaseRow;d:=json.NewDecoder(bytes.NewReader(plain));d.DisallowUnknownFields();if d.Decode(&x)!=nil||x.ID!=string(k){return errors.New("record invalid")};leases=append(leases,x);return nil})});db.Close();if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};sort.Slice(leases,func(i,j int)bool{return leases[i].ID<leases[j].ID});if len(leases)!=len(tokens){fmt.Fprintln(os.Stderr,"reconciliation count");panic("audit failed")};for i:=range leases{t,l:=tokens[i],leases[i];if l.ID!=t.LeaseID||l.Subject!=t.Subject||l.Kid!=t.Kid||l.ExpiresAt!=t.Exp{fmt.Fprintln(os.Stderr,"reconciliation mismatch");panic("audit failed")}};mr,e:=modules(*mods);if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")};out:=report{tokens,leases,mr};data,_:=json.MarshalIndent(out,"","  ");parent:=filepath.Dir(*dest);f,e:=os.CreateTemp(parent,".locksmith-report-");if e!=nil{panic(e)};name:=f.Name();defer os.Remove(name);if _,e=f.Write(append(data,'\n'));e==nil{e=f.Sync()};if ce:=f.Close();e==nil{e=ce};if e==nil{e=os.Rename(name,*dest)};if e!=nil{fmt.Fprintln(os.Stderr,e);panic("audit failed")}
}
