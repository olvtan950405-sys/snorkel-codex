package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	bolt "go.etcd.io/bbolt"
)

type key struct{ id string; pub ed25519.PublicKey; priv ed25519.PrivateKey }
var mu sync.Mutex
var keys []key

func fresh(id string) key { p,q,_:=ed25519.GenerateKey(rand.Reader); return key{id,p,q} }
func main() {
	dbPath:=os.Getenv("LOCKSMITH_DB"); if dbPath=="" { dbPath=filepath.Join(os.TempDir(),"locksmith.db") }
	master:=[]byte(os.Getenv("LOCKSMITH_MASTER_KEY")); if len(master)!=32 { panic("LOCKSMITH_MASTER_KEY must be 32 bytes") }
	db,err:=bolt.Open(dbPath,0600,nil); if err!=nil { panic(err) }; defer db.Close()
	keys=[]key{fresh("k1")}; gin.SetMode(gin.ReleaseMode); r:=gin.New()
	r.GET("/.well-known/jwks.json",func(c *gin.Context){ mu.Lock(); defer mu.Unlock(); out:=[]any{}; for _,k:=range keys { out=append(out,map[string]any{"kid":k.id,"kty":"OKP","crv":"Ed25519","alg":"EdDSA","use":"sig","x":base64.RawURLEncoding.EncodeToString(k.pub)}) }; c.JSON(200,map[string]any{"keys":out}) })
	r.POST("/rotate",func(c *gin.Context){ mu.Lock(); defer mu.Unlock(); keys=append(keys,fresh(fmt.Sprintf("k%d",len(keys)+1))); c.JSON(200,map[string]any{"kid":keys[len(keys)-1].id}) })
	r.POST("/leases",func(c *gin.Context){ var in struct{ID,Subject string; TTL int64}; if c.BindJSON(&in)!=nil || in.ID=="" || in.Subject=="" { c.Status(400); return }; mu.Lock(); k:=keys[len(keys)-1]; mu.Unlock(); now:=time.Now().Unix(); tok:=jwt.NewWithClaims(jwt.SigningMethodEdDSA,jwt.MapClaims{"sub":in.Subject,"lease_id":in.ID,"iss":"locksmith","aud":"lease-clients","iat":now,"exp":now+in.TTL}); tok.Header["kid"]=k.id; signed,_:=tok.SignedString(k.priv)
		plain,_:=json.Marshal(map[string]any{"id":in.ID,"subject":in.Subject,"kid":k.id,"expires_at":now+in.TTL}); block,_:=aes.NewCipher(master); g,_:=cipher.NewGCM(block); nonce:=make([]byte,g.NonceSize()); rand.Read(nonce); blob:=g.Seal(nonce,nonce,plain,[]byte(in.ID)); db.Update(func(tx *bolt.Tx) error { b,_:=tx.CreateBucketIfNotExists([]byte("leases")); return b.Put([]byte(in.ID),blob) }); c.JSON(201,map[string]any{"token":signed}) })
	ln,err:=net.Listen("tcp","127.0.0.1:0"); if err!=nil { panic(err) }; fmt.Printf("LISTENING %s\n",ln.Addr()); os.Stdout.Sync(); http.Serve(ln,r)
}
