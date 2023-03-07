__version__ = '0.0.0'

from typing import (
    TypeVar, 
    ForwardRef, 
    Optional,
    Union,
    Tuple,
    Iterable, 
    Callable,
    TYPE_CHECKING,
)
from dataclasses import dataclass
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from uuid import uuid1


if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


Tensor = TypeVar('Tensor', bound=ForwardRef('numpy.ndarray'))

class Client(ABC):

    def __init__(self,
                 gateway: str = 'localhost:8080'):
        '''Instantiate a client.
        
        'gateway' specifies a gateway address to invoke endpoints from remote
        executors. The default gateway directs to localhost:8080.
        '''
        self.gateway = gateway


    @abstractmethod
    def post(self, on: str, docs: Optional['DocArray'] = None) -> Optional['DocArray']:
        '''Posts a docarray to the endpoint speicified by 'on' via the gateway.
        '''
        ...

    @abstractmethod
    def stream(self, on: str) -> 'Stream':
        '''Creates a stream used to send/recv to/from an enpoint via the gateway.
        '''
        ...


class NoopClient(Client):

    def post(self, on: str, docs: Optional['DocArray'] = None) -> Optional['DocArray']:
        raise NotImplementedError
    
    def stream(self, on: str) -> 'Stream':
        raise NotImplementedError



class Doc(ABC):
    '''A class with some abstract methods to represent model input or output.'''

    def __init__(self, 
                 *, 
                 id: str = uuid1(),
                 uri: Optional[str] = None):
        self.id = id
        self.uri = uri
        self._blob = None
        self._tensor = None

    
    @property
    def tensor(self) -> Tensor:
        if self._tensor:
            return self._tensor
        return self.to_tensor()


    @property
    def blob(self) -> bytes:
        if self._blob:
            return self._blob
        return self.to_blob()


    # @abstractmethod
    # def to_blob(self) -> bytes: ...


    # @abstractmethod
    # def from_blob(self): ...


    # @abstractmethod
    # def to_tensor(self) -> Tensor: ...


    # @abstractmethod
    # def from_tensor(self): ...


class DocArray:

    def __init__(self, docs: Iterable[Doc]):
        self.docs = docs

    def __iter__(self):
        for d in self.docs:
            yield d



class Text(Doc):

    def __init__(self, *, # disable positional arguments
                 text: Optional[str] = None, 
                 uri: Optional[str] = None):
        self.text = text
        super().__init__(uri=uri)
        

class Image(Doc):

    def __init__(self, *, # disable positional arguments
                 image: Optional["PILImage"] = None,
                 uri: Optional[str] = None):
        self.image = image
        super().__init__(uri=uri)



def post(func: Optional[Callable[['Executor', 'DocArray'], Optional['DocArray']]] = None, 
         batch_size: Optional[int] = None,
         timeout: Optional[int] = None,
         on: Optional[str] = None):
    '''Returns a Executor method as a post handler.
    
    Example:
    >>> from typing import Optional
    >>>
    >>> class MyExecutor:
    >>>     @post
    >>>     def echo(self, docs: DocArray) -> Optional[DocArray]:
    >>>         return docs
    '''

    def wrap(func):
        # TODO: maintain state
        def __call__(self: 'Executor', docs: 'DocArray') -> Optional[DocArray]:
            # TODO: batching if batch_size > 1
            return func(self, docs)
        return __call__
    
    if func is None:
        # we are being used as @on()
        return wrap
    
    # we are being used as @on
    return wrap(func)


def stream(func: Optional[Callable[['Executor', 'Stream'], None]]):
    '''Returns a Executor method as a stream handler.
    '''
    def wrap(func):
        def __call__(self: 'Executor', stream: 'Stream') -> None:
            return func(self, stream)
        
        return __call__
    
    if func is None:
        # we are being used as @on()
        return wrap
    
    # we are being used as @on
    return wrap(func)


class Stream: ...

class Executor:

    def __init__(self,
                 *,
                 name: Optional[str] = None,
                 client: Optional['Client'] = None,
                 post_endpoints: Optional[Iterable[str]] = None,
                 stream_endpoints: Optional[Iterable[str]] = None,):
        '''Instantiate an executor.
        'post_endpoints'
        '''
        self.name = name
        self.client = client

        if self.client is None:
            self.client = NoopClient()

        # Inject endpoints dynamically so that they can be accessed by self.post
        # using getattr.
        if post_endpoints:
            for ep in post_endpoints:
                setattr(self, ep, lambda docs: self.client.post(ep, docs=docs))
        if stream_endpoints:
            for ep in stream_endpoints:
                setattr(self, ep, lambda: self.client.stream(ep))


    def post(self, on: str, docs: Optional[DocArray] = None) -> Optional[DocArray]:
        '''Invokes an endpoint specified by 'on'.

        The reason why we use getattr every time this method is called is that
        an executor can hold both endpoints itself (accessed by self) and
        endpoints via a gateway using a client.
        '''
        try:
            func = getattr(self, on)
            return func(docs)
        except AttributeError:
            return self.client.post(on, docs)
        

    
    def stream(self, on: str) -> Stream: raise NotImplementedError


class Flow:

    def __init__(self,
                 client: Optional[Client] = None):
        self.nodes = {}
        self.edges = {}
        self.client = client

    def add(self, 
            use: Union[Executor, str],
            on: Optional[str] = None,
            key: Optional[str] = None,
            needs: Optional[Iterable[str]] = None,
            reduce: bool = False) -> 'Flow':
        '''Adds an executor to the flow with optionally specified dependencies.
        
        This method takes an executor or a URI to it and inserts it into a DAG
        aka. Directed Acyclic Graph, taking 'needs' as links coming from those
        that finish executing before the one being added. NOTE that 'on' must
        be specified if 'use' is an instance of Executor to tell the DAG the
        endpoint to used.
        '''
        if isinstance(use, Executor):
            if on is None:
                raise ValueError(f"'on' must be specified when 'use' is an instance of Execcutor")
            key = '/'.join(use.name, on)
        elif isinstance(use, str):
            key = use
            url = urlparse(use)
            name, endpoint = _parse_path(url.path[1:])
            use = Executor(name=name,
                           gateway=url.netloc,
                           client=self.client,
                           post_endpoints=(endpoint,))
        else:
            raise TypeError(f"'use' can only be an instance of either Executor or str")
        
        self.nodes[key] = use
        self.edges[key] = needs
        
        if reduce:
            raise NotImplementedError


    async def post(self, docs: Optional[DocArray] = None) -> Optional[DocArray]:
        '''Fires the flow of executors and wait until the last executor finishes.
        '''
        raise NotImplementedError



def _parse_path(path: str) -> Tuple[str, str]:
    i = path.find('/')
    return path[:i], path[i+1:]


if __name__ == '__main__':
    from dataclasses import dataclass

    class MyExecutor(Executor):
        @post
        def echo(self, docs: DocArray) -> Optional[DocArray]:
            return docs


    @dataclass
    class YourDoc:
        text: Text


    @dataclass
    class MyDoc:
        image: Image
        text: Text
        your: YourDoc


    req_d = MyDoc(
        text=Text(text='Aa'), 
        image=Image(uri='a.jpg'),
        your=YourDoc(text=Text(text='Bb')),
    )
    
    
    s = MyExecutor(name='my_Executor', post_endpoints=['ping'])
    res_d = s.ping(req_d)
    print(res_d)