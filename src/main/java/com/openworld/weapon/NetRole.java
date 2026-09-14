package com.openworld.weapon;

import com.openworld.net.NetworkManager;
import godot.api.Node;

/** Which side of a networked session this peer is on, read off the NetworkManager AutoLoad. */
final class NetRole {

    private NetRole() { }

    static NetworkManager net(Node from) {
        return from.getNodeOrNull("/root/NetworkManager") instanceof NetworkManager n ? n : null;
    }

    /** A networked non-host peer: its attacks are predicted locally and resolved by the host. */
    static boolean client(Node from) {
        NetworkManager n = net(from);
        return n != null && n.isNetworked() && !n.isServer();
    }

    /** The host of a networked session. */
    static boolean host(Node from) {
        NetworkManager n = net(from);
        return n != null && n.isNetworked() && n.isServer();
    }
}
