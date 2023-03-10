![logo.png](./docs/logo.png)

![GitHub issues](https://img.shields.io/github/issues/xoolab/ui)
![license](https://img.shields.io/github/license/xoolab/ai)

A lightweight and pluggable tookit to put multiple ML models into production.

## Want to contribute?

xooai is now under hot development, you need to first read the design below before driving in then clone or fork this repo and start hacking in dev mode, or join the discussion [here](https://github.com/xoolab/ai/discussions).

To get started in dev mode, run

```bash
git clone https://github.com/xoolab/ai.git
pip install -e .
```

## Design

Let's first go for a quick view on the design of xooai :)

### Core Concepts

We take [docarray](https://github.com/docarray/docarray)'s excellent approach for the three core concepts as follows but there are some differences in the implementation that you will see. 

- Doc
- Executor
- Flow

Each takes a higher level of abstraction from the previous one.

#### Doc

The biggest problem so far has been the generalization of model data flows, a way to put different kinds of ML inputs and outputs into a unified representation in code. Here's how we do it.

```python
from xooai import Text

t1 = Text(ref='233.jpg')
t2 = Text(ref='https://some.domain/233.jpg')
```

or from some ready text

```python
t3 = Text(text='Aa')
```

`Text` is subclassed from `Doc` a class with abstract methods to represent ML inputs or outputs. We have provided a few other subclasses that we use the most often in our researches, and you are welcome to PR for more rarely used data types.

- Text
- Image
- Audio
- Video

All subclasses derive an attribute named `ref` from the base class `Doc` to specify a resource to be fetched when needed.

You can also struct your own Doc with these subclasses and even nest it.

```python
from xooai import Text, Image, Video, doc

@doc
class YourDoc:
    video: Video

@doc
class MyDoc:
    text: Text
    image: Image
    your: YourDoc
```

Note that you have to decorate your class with `doc`, an alias of `dataclass` implementated by [pydantic](https://pydantic.dev) that has support for attribute validation.


#### Executor

The next level of abstraction is called an executor, a hybrid structure that has endpoints defined in it to handle specific requests.

We use the term `hybrid`, because an executor is both the client and the server of a model service. You will see why such an approach. Right Now let's just take a look at a simple example of how to use an executor.

```python
from xooai import Executor, post

class MyExecutor(Executor):
    @post
    def echo(self, docs: DocArray):
        return docs


with MyExecutor(name='my_executor') as e: # we prefer lower snake case :)
    e.run()
```

The Executor has implementated methods to send and receive requests from another executor (remember we said it's hybrid?), so we need to subclass our own executor `MyExecutor` from it, but the program under the hood does not know where to dispatch received requests yet, therefore, we define the endpoint handler, named `echo` in our case, in our executor, it simply returns the docs received to its caller without modifying it. *You must have realized that the endpoint handler is where we call our trained model and return the result as another DocArray instance :)*

Then we call `run` from our executor instance that blocks until a signal is caught. Our first little executor is up!

Note that here we use a new class named `DocArray`, don't worry, it's just a regular class simply subclassed from a list of `Doc`s we have talked about, to represent a series of, say inputs.

> Should we have the argument of endpoint handlers limited to a DocArray or either a DocArray or any number of `Doc`s (or its subclasses)?
>

Now it's time for y'all to understand what is called a hyrid executor and why it is needed. 

Consider a scenario where we are developing an endpoint handler in an executor and want to checkout if it works. We don't actually need to do any network workaround, all we need is just an in-process call to the endpoint handler as follows.

```python
from xooai import Executor, post

class MyExecutor(Executor):
    @post
    def echo(self, docs: DocArray):
        return docs

e = MyExecutor(name='my_executor')
res = e.post(on='echo', docs=DocArray())
```

The last line makes an in-process mocking invocation to the `echo` endpoint. Wait! Why don't we just make the call like

```python
res = e.echo(docs=DocArray())
```

You are right! We can make a direct call to the echo method, but we are testing whether a request can be transmitted to the endpoint handler via the whole call stack, aren't we?

Alright, we will see a more practical example in the next section - the Flow!

#### Flow

Putting ML models into production is not about just building one single server to wrap a trained model, remember the old days struggling with Flask? :)

ML model services are functions after all, and functions should be able to be composed to form a new function, a higher-order function if you like the term. Now that our executor holds one or more functions in it, we need, again, a higher level of abstraction over the executor to make endpoint handlers composable, hence we have the Flow coming up.

```python
from xooai import Flow, Executor, post

class MyExecutor(Executor):
    @post
    def echo(self, docs: DocArray):
        return docs


f = Flow()
f.add(use='https://some.domain/your_executor/echo', id='e1')
f.add(use='https://some.domain/her_executor/echo', id='e2')
f.add(use=MyExecutor, on='echo', id='e3', needs=('e1', 'e2'))

res = f.post(docs=DocArray())
```

As you can see, a flow is like a pipeline consist with multiple excutors. In this case, we added three executors into a flow, each of them is indexed by an `id` argument. e3 is our self-defined executor that has an extra argument called `needs` to tell the flow scheduler that e3 can be executed only after e1 and e2 are finished. This is why we call it a pipeline :)

Yea~ e1 and e2 are executors running in the cloud or a remote host in our local network, this can be done possible due to our hyrid design of executors!
In other words, e1 and e2 and executors as clients instead of servers as shown in the previous cases.

Additionally, a flow can be specified a gateway address as follows, by doing so, can headless executors inherit a gateway address from the flow it belongs to.

```python
f = Flow(gateway='https://some.domain')
```

The flow in the example above can be shown as

```
              +------+
          +-> |  e1  | --+
+-----+   |   +------+   |   +------+    +-----+
|  f  | --+              +-> |  e3  | -> |  f  |
+-----+   |   +------+   |   +------+    +-----+
          +-> |  e2  | --+
              +------+
```

which looks awesome, doesn't it? :)

### Driver

We have mentioned the client and server a lot previously on this documentation. These two are the programs under the hood to transmit docarraies between executors and are abstracted as an interface called `Driver` represented using the abstract class in Python so that xooai users can choose different implementations depending on their needs.

There are so many execellent Python libraries that focus on C/S and RPC stuff like [FastAPI](https://fastapi.tiangolo.com/) who has native support for [Swagger](https://swagger.io/), or [gRPC](http://grpc.io) that uses HTTP/2 to maintain connections.

We are going to provide three driver implementations listed below.

- HTTP driver - built right upon [uvicorn](https://www.uvicorn.org/) to make the driver light-weight and efficient.
- gRPC driver - using [gRPC](http://grpc.io) and the [protobuf](https://protobuf.dev) toolchain.
- QUIC driver - [aiooquic](https://github.com/aiortc/aioquic) potentially .


All driver implementations should have support for both JSON and [msgpack](https://msgpack.org) to (de)serialize data over the drivers themselves, and are placed in subdirectory - [drivers](./xooai/drivers/).

To use xooai with the HTTP driver for example, run

```bash
pip install xooai[http]
```

You are welcome to PR more driver implementation based on the tool you like.

### Storage

One of the differences between a regular HTTP service and a ML model service is that the later one often has to handle a large chunk of request like a set of HQ images and a large video. We used to solve this by using a thirding-party OSS - aka. object storage service, public or self-hosted like [MinIO](https://min.io).

Given that, a doc has to be associated with a unique path under an OSS, which leads us to another abstraction within Doc - the Store interface.

`Store` has two abstract methods - `put` to upload a file to a server and `get` to download a file from that server. The server needs to be accesable for both the executors.

For example, when an executor is going to post a doc of a large file, it calls the store interface to put the file to a server the interface is implemented for before it actually post the doc, and the executor receiving the doc will get that file from the same server then cache it if needed.

A doc can curry a signature of the file so that the executor receiving the doc can compare the signature from its cache to see if it has to call the store interface to get the file, or just reuse from its cache.


### Cloud Native

The sencond largest pain in the *ss is how we can shift our models into a cloud-native environment. Even with xooai now, it is still not clear how.

Having been working on [Go](https://go.dev) and microservices for a long while, we realize that it is a have-to-go step to make if we want to build a serverless function platform for ML models and get the concepts of [FaaS](https://en.wikipedia.org/wiki/Function_as_a_Service) done. All we need now is again another level of abstract over the Flow, an API gateway in front of all the flows running as OCI containers, thus leading us to:

- A multi-tenancy platform with an API gateway to publish and consume xooai executors.
- A CLI to generate Dockerfile and Kubernetes configuration files for the platform to build and deploy xooai executors automatically.
- A set of services to orchestrate the entire platform itself.
- A public website as the UI of the platform for online invocation and executor management, flow management, application management, etc.

### Microservices

You may have noticed that the design of the three core concepts actually makes xooai a microservice framework (in fact we prefer the term structurized-services) but with request and response limited to a Doc structure. It is! Have you ever had the idea that almost every software engineering or system architecting is essentially doing two things - **synchronous bidirectional streaming** and **asynchronous messaging**, no matter whether it is service intercommunication or interaction with databases. This is why most of the system look the same under the table.

The synchronous bidirectional streaming can derive into three sub-calls - 1) unary call, the one we do the most often with HTTP. 2) client-side streaming, used when we upload a large bunch of data, like a video, to the server and get a single response from it. 3) server-side streaming, used when we download a hell lot of data from a server and acknowledge it with a single response.

[gRPC](http://grpc.io) has been implemented right upon such concept. It used HTTP/2 in its transport layer for full-deplex communication between services and split out the three other communication models from it. [micro](https://micro.dev) has gone far beyond that, it made a lot of abstraction over services and networks in distributed systems and integrated them into a serverless, environment-agnostic service platform, along with its support for asynchronous messaging, which is exciting.

Asynchronous messaging is more interesting and really useful in some specific scenarios. It uses a communication model called subscribe/publish to decouple system architecture and smooth the data flow in a busy service network. We love to use it for system monitoring since it does not entangle with the functionalities of the system itself.

Those two abstractions made a conclusion on communication in different kinds of software and distributed systems. It is like what James Clerk Maxwell has done for electromagnetic physics. Therefore we also hope to have a grand unified framework for any service development just like physicists since Albert Einstein wish for physics. With such a framework, it is no longer needed to spend a hell lot of time on design every time when developers want to build something, no matter if it is a monolithic system or distributed one. They just need to write code.

By now, [micro](https://micro.dev) is the most promising one.

## License

xooai is Apache 2.0 licensed.
